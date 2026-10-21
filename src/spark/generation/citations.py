"""Citation validation hardening (Phase 10)."""

from __future__ import annotations

import re
from collections import defaultdict

from spark.generation.numeric import answer_numerics_subset_of_context, extract_numerics
from spark.generation.schemas.safety_answer import SafetyAnswerSchema
from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER
from spark.retrieval.models import RetrievedDoc
from spark.generation.parent_context import doc_chunk_id, generation_context_for_doc
from spark.retrieval.synthesis import _split_sentences

from .context import chunk_id_map

CHUNK_CITATION_RE = re.compile(r"\[chunk_id:([^\]]+)\]", re.IGNORECASE)
_HEADER_LINE_RE = re.compile(r"^#+\s")


def split_citation_ids(raw: str) -> list[str]:
    """Normalize one citation marker's payload into individual chunk ids.

    Models legitimately combine citations into one marker —
    "[chunk_id:a, chunk_id:b]" — and treating that payload as a single id
    fails the doc lookup, flagging a correctly-cited answer as unverified.
    """
    out: list[str] = []
    for piece in (raw or "").split(","):
        cleaned = piece.strip()
        if cleaned.lower().startswith("chunk_id:"):
            cleaned = cleaned[len("chunk_id:"):].strip()
        if cleaned:
            out.append(cleaned)
    return out


def find_cited_ids(text: str) -> list[str]:
    """All chunk ids cited in *text*, in order, combined markers expanded."""
    ids: list[str] = []
    for raw in CHUNK_CITATION_RE.findall(text or ""):
        ids.extend(split_citation_ids(raw))
    return ids


MAX_UNCITED_SENTENCE_RATIO = 0.20
SAFETY_MAX_UNCITED_SENTENCE_RATIO = 0.0


def _sentence_requires_citation(sentence: str) -> bool:
    stripped = CHUNK_CITATION_RE.sub("", sentence or "").strip()
    if len(stripped) < 8:
        return False
    if _HEADER_LINE_RE.match(stripped):
        return False
    if stripped.casefold().startswith("อ้างอิง"):
        return False
    if stripped.startswith("พบข้อมูลที่เกี่ยวข้อง"):
        return False
    if stripped.startswith("สรุปนี้ยึดตามข้อความ"):
        return False
    if stripped in (NO_DATA_ANSWER, UNAVAILABLE_ANSWER):
        return False
    return True


_ADVISORY_RE = re.compile(
    r"(ควร|แนะนำ|เพื่อป้องกัน|เพื่อความปลอดภัย|should|recommend|it is advisable|to prevent)",
    re.IGNORECASE,
)


def _is_advisory_sentence(sentence: str) -> bool:
    """A soft recommendation ('should check…') rather than a factual claim.

    Such a closing reminder is often not literally in the manual; allowing a
    single uncited one (non-safety questions only) keeps otherwise fully-cited
    answers from being discarded, while any second uncited claim still fails.
    """
    stripped = CHUNK_CITATION_RE.sub("", sentence or "").strip()
    return bool(_ADVISORY_RE.search(stripped))


def _sentences_covered_by_cited_blocks(answer: str) -> set[str]:
    """Sentences grounded by a trailing citation within their line/paragraph.

    LLMs legitimately cite at paragraph or list-item level ("fact A. fact B.
    [chunk_id:x]") — the trailing marker grounds the text BEFORE it. Requiring
    a marker on each individual sentence rejected correct, verifiable answers
    purely for formatting style. Sentences appearing AFTER a block's last
    citation are not covered — an uncited tail stays uncited.
    """
    covered: set[str] = set()
    for block in (answer or "").split("\n"):
        markers = list(CHUNK_CITATION_RE.finditer(block))
        if not markers:
            continue
        cited_prefix = block[: markers[-1].end()]
        for sentence in _split_sentences(cited_prefix):
            stripped = sentence.strip()
            if stripped:
                covered.add(stripped)
    return covered


def _is_extractive_template(answer: str) -> bool:
    return (answer or "").strip().startswith("พบข้อมูลที่เกี่ยวข้อง")


def _validate_extractive_template_citations(
    answer: str,
    docs: list[RetrievedDoc],
) -> tuple[bool, list[RetrievedDoc]]:
    id_map = chunk_id_map(docs)
    cited_docs: list[RetrievedDoc] = []
    bullet_lines = 0
    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        bullet_lines += 1
        ids = find_cited_ids(stripped)
        if not ids:
            return False, []
        for raw_id in ids:
            doc = id_map.get(raw_id.strip().lower())
            if doc is None:
                return False, []
            if doc not in cited_docs:
                cited_docs.append(doc)
    if bullet_lines == 0:
        return False, []

    context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs)
    stripped_answer = CHUNK_CITATION_RE.sub("", answer)
    if not answer_numerics_subset_of_context(stripped_answer, context):
        return False, []
    return True, cited_docs


_CITATION_SEGMENT_RE = re.compile(r"(.*?)\[chunk_id:([^\]]+)\]", re.IGNORECASE | re.DOTALL)


def _has_contradictory_chunk_citations(
    answer: str,
    docs: list[RetrievedDoc] | None = None,
) -> bool:
    """True when a cited chunk carries conflicting values for the same unit (e.g. 80°C vs 85°C).

    Numbers are attributed to the citation marker that FOLLOWS them on the same
    line — the way answers are actually written ("fact 3000 rpm [chunk_id:a]
    ส่วนรุ่น B 5000 rpm [chunk_id:b]"). Sentence-level attribution broke Thai
    comparisons: Thai has no sentence-final periods, so a multi-line comparison
    collapsed into one "sentence" whose two legitimate values looked like one
    chunk contradicting itself.

    Two same-unit values under one chunk are only a contradiction when the
    chunk's own text can't account for them. A wiring-diagram or spec-table
    chunk legitimately carries many same-unit ratings (motor 0.2 kW next to
    its 0.37 kW drive) — an answer quoting two of those is correct, not
    self-contradictory, so when *docs* are given the values are checked
    against the cited chunk's context before failing.
    """
    by_chunk: dict[str, dict[str, set[float]]] = defaultdict(lambda: defaultdict(set))
    for line in (answer or "").split("\n"):
        for match in _CITATION_SEGMENT_RE.finditer(line):
            segment_text, raw_id = match.group(1), match.group(2)
            nums = extract_numerics(segment_text)
            if not nums:
                continue
            for cid in (c.lower() for c in split_citation_ids(raw_id)):
                for token in nums:
                    if not token.unit:
                        continue
                    by_chunk[cid][token.unit].add(round(token.value, 3))
    id_map = chunk_id_map(docs) if docs else {}
    for cid, unit_map in by_chunk.items():
        for unit, values in unit_map.items():
            if len(values) <= 1:
                continue
            doc = id_map.get(cid)
            if doc is None:
                return True
            context_values = {
                round(token.value, 3)
                for token in extract_numerics(generation_context_for_doc(doc))
                if token.unit == unit
            }
            if not values.issubset(context_values):
                return True
    return False


def _max_uncited_ratio(question: str | None) -> float:
    """Return 0.0 for safety-critical content, standard ratio otherwise."""
    if question is None:
        return MAX_UNCITED_SENTENCE_RATIO
    from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent

    safety = detect_safety_intent(question)
    if safety.kind != SafetyIntentKind.NONE:
        return SAFETY_MAX_UNCITED_SENTENCE_RATIO
    return MAX_UNCITED_SENTENCE_RATIO


def _numeric_whitelist_question(question: str | None) -> str | None:
    """Question text whose numerics the numeric gate may treat as grounded.

    None for safety-intent and explicit-limit questions — there, echoing the
    asker's own number ("สูงสุด 95 ใช่ไหม" → "ใช่ครับ 95") is the fabrication
    this gate must keep blocking."""
    if not question:
        return None
    from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent
    from spark.retrieval.scoring import _question_requires_explicit_limit_evidence

    if detect_safety_intent(question).kind != SafetyIntentKind.NONE:
        return None
    if _question_requires_explicit_limit_evidence(question):
        return None
    return question


def validate_grounded_citations(
    answer: str,
    docs: list[RetrievedDoc],
    *,
    question: str | None = None,
) -> tuple[bool, list[RetrievedDoc]]:
    """Every substantive sentence must cite a chunk_id present in docs."""
    if not answer or answer in (NO_DATA_ANSWER, UNAVAILABLE_ANSWER):
        return False, []

    cited_ids = find_cited_ids(answer)
    if not cited_ids:
        return False, []

    if _has_contradictory_chunk_citations(answer, docs):
        return False, []

    if _is_extractive_template(answer):
        return _validate_extractive_template_citations(answer, docs)

    id_map = chunk_id_map(docs)
    cited_docs: list[RetrievedDoc] = []
    for raw_id in cited_ids:
        doc = id_map.get(raw_id.strip().lower())
        if doc is None:
            return False, []
        if doc not in cited_docs:
            cited_docs.append(doc)

    max_ratio = _max_uncited_ratio(question)
    required_sentences = [
        sentence
        for sentence in _split_sentences(answer)
        if _sentence_requires_citation(sentence)
    ]
    if required_sentences:
        uncited = [
            sentence
            for sentence in required_sentences
            if not CHUNK_CITATION_RE.search(sentence)
        ]
        # Paragraph-level credit (non-safety): a sentence inside a block that
        # carries a citation is grounded by that block's citation. Safety keeps
        # per-sentence strictness via max_ratio == 0.0 below.
        if max_ratio > 0.0 and uncited:
            covered = _sentences_covered_by_cited_blocks(answer)
            uncited = [s for s in uncited if s.strip() not in covered]
        # For non-safety answers, tolerate a single uncited *advisory* sentence
        # (e.g. a closing "should check the cooling system" reminder). Safety
        # questions keep max_ratio == 0.0, so this never loosens them, and any
        # second uncited claim — or an uncited factual one — still fails.
        if (
            max_ratio > 0.0
            and len(uncited) == 1
            and _is_advisory_sentence(uncited[0])
        ):
            uncited = []
        if required_sentences and len(uncited) / len(required_sentences) > max_ratio:
            return False, []

    context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs)
    stripped_answer = CHUNK_CITATION_RE.sub("", answer)
    if not answer_numerics_subset_of_context(
        stripped_answer, context, question=_numeric_whitelist_question(question)
    ):
        return False, []

    return True, cited_docs


def _cited_docs_for_answer(answer: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc] | None:
    cited_ids = find_cited_ids(answer)
    if not cited_ids:
        return None
    id_map = chunk_id_map(docs)
    cited_docs: list[RetrievedDoc] = []
    for raw_id in cited_ids:
        doc = id_map.get(raw_id.strip().lower())
        if doc is None:
            return None
        if doc not in cited_docs:
            cited_docs.append(doc)
    return cited_docs


def citation_validation_failure(
    answer: str,
    docs: list[RetrievedDoc],
    *,
    question: str | None = None,
) -> str | None:
    """Return a specific failure reason when citation validation fails."""
    if not answer or answer in (NO_DATA_ANSWER, UNAVAILABLE_ANSWER):
        return None
    if _has_contradictory_chunk_citations(answer, docs):
        return None
    cited_docs = _cited_docs_for_answer(answer, docs)
    if cited_docs is None:
        return None
    numeric_question = _numeric_whitelist_question(question)
    if _is_extractive_template(answer):
        ok, _ = _validate_extractive_template_citations(answer, docs)
        if not ok:
            stripped_answer = CHUNK_CITATION_RE.sub("", answer)
            context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs)
            if not answer_numerics_subset_of_context(
                stripped_answer, context, question=numeric_question
            ):
                return "numeric_grounding_fail"
        return None

    required_sentences = [
        sentence
        for sentence in _split_sentences(answer)
        if _sentence_requires_citation(sentence)
    ]
    if required_sentences:
        uncited = [
            sentence
            for sentence in required_sentences
            if not CHUNK_CITATION_RE.search(sentence)
        ]
        # Fixed lenient threshold (not the safety-strict ratio): this guard only
        # decides "is the failure dominated by missing citations?" If we used the
        # safety 0.0 here, any single uncited sentence in a safety answer would
        # return None and bypass the numeric-fabrication check below — exactly
        # backwards. Over-detecting numeric fabrication for safety is the safe bias.
        max_ratio = _max_uncited_ratio(None)
        if len(uncited) / len(required_sentences) > max_ratio:
            return None

    stripped_answer = CHUNK_CITATION_RE.sub("", answer)
    context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs)
    if not answer_numerics_subset_of_context(
        stripped_answer, context, question=numeric_question
    ):
        return "numeric_grounding_fail"
    return None


def validate_structured_safety_citations(
    schema: SafetyAnswerSchema,
    docs: list[RetrievedDoc],
) -> tuple[bool, list[RetrievedDoc]]:
    """Validate structured safety citations against retrieved docs."""
    if not schema.steps or not schema.citations:
        return False, []
    id_map = chunk_id_map(docs)
    cited_docs: list[RetrievedDoc] = []
    for ref in schema.citations:
        doc = id_map.get(ref.chunk_id.strip().lower())
        if doc is None:
            return False, []
        if doc not in cited_docs:
            cited_docs.append(doc)
    combined = "\n".join([*schema.steps, *schema.warnings])
    context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs)
    if not answer_numerics_subset_of_context(combined, context):
        return False, []
    return True, cited_docs


def collect_source_spans(cited_docs: list[RetrievedDoc], spans) -> list[dict]:
    out: list[dict] = []
    cited_ids = {doc_chunk_id(d).lower() for d in cited_docs if doc_chunk_id(d)}
    for span in spans:
        if span.chunk_id.lower() in cited_ids:
            out.append(span.as_source_span())
    return out
