from __future__ import annotations

# Many private helpers are imported from scoring because this is a mechanical split
# of the pre-existing RAG answer synthesis logic.
# ruff: noqa: F403,F405
import re
from typing import Any

from spark.schemas.rag import coerce_source_page
from spark.services.reranker import lexical_overlap_score

from .constants import *
from .models import RetrievedDoc
from .scoring import *

def _thai_ratio(text: str) -> float:
    if not text:
        return 0.0
    thai = len(_THAI_RE.findall(text))
    return thai / max(1, len(text))


def _latin_word_ratio(text: str) -> float:
    words = _LATIN_WORD_RE.findall(text or "")
    if not words:
        return 0.0
    return len(words) / max(1, len(text.split()))


def _extract_substantive_numbers(text: str) -> set[str]:
    return {m.lower() for m in _SUBSTANTIVE_NUMBER_RE.findall(text or "")}


def _answer_has_hallucinated_numbers(answer: str, context: str) -> bool:
    answer_nums = _extract_substantive_numbers(answer)
    if not answer_nums:
        return False
    context_nums = _extract_substantive_numbers(context)
    return bool(answer_nums - context_nums)


def _answer_too_english_for_thai_question(question: str, answer: str) -> bool:
    if _thai_ratio(question) < 0.05:
        return False
    return _latin_word_ratio(answer) > 0.35 and _thai_ratio(answer) < 0.12


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"[\u2013\u2014-]\s*\n\s*", " — ", text or "")
    cleaned = re.sub(r"(?<![.!?])\n\s*(?=\S)", " ", cleaned)
    parts = _SENTENCE_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p and p.strip()]


def _score_evidence_text(question: str, doc: RetrievedDoc, text: str) -> float:
    payload = {**doc.payload, "page_content": text}
    keyword = _keyword_recovery_score(question, payload)
    lexical = min(1.0, lexical_overlap_score(question, text) * 12)
    thai_overlap = 0.0
    q_grams = _thai_char_ngrams(question)
    t_grams = _thai_char_ngrams(text)
    if q_grams and t_grams:
        thai_overlap = len(q_grams & t_grams) / len(q_grams)
    return max(keyword, lexical, thai_overlap * 0.85)


def _collapse_horizontal_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs but keep line breaks.

    PDF table extraction (pdf_tables.py) emits well-formed markdown tables
    with one row per line. Collapsing all `\\s+` (the old behavior) ate the
    row boundaries too, turning a table into one unreadable wall of `|`
    characters — this keeps rows intact for both the raw chunk text and the
    citation UI's markdown table renderer.
    """
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines())
    return "\n".join(line for line in lines if line)


def _trim_evidence_text(text: str, max_chars: int = 420) -> str:
    cleaned = _collapse_horizontal_whitespace((text or "").strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _evidence_snippets_for_doc(
    question: str,
    doc: RetrievedDoc,
    *,
    max_snippets: int = 2,
) -> list[tuple[str, float]]:
    candidates = _split_sentences(doc.page_content)
    if not candidates:
        candidates = [doc.page_content or ""]
    colon_lines = [
        line for line in (doc.page_content or "").splitlines() if ":" in line and line.strip()
    ]
    if (
        doc.payload.get("source_sheet")
        or doc.payload.get("row_number") is not None
        or len(colon_lines) >= 2
    ):
        candidates = [doc.page_content or "", *candidates]

    scored: list[tuple[str, float, int]] = []
    seen_candidates: set[str] = set()
    for idx, raw in enumerate(candidates):
        snippet = _trim_evidence_text(raw)
        if len(snippet) < 3:
            continue
        if snippet.lower() in seen_candidates:
            continue
        seen_candidates.add(snippet.lower())
        score = _score_evidence_text(question, doc, snippet)
        if score >= MIN_EXTRACTIVE_EVIDENCE_SCORE:
            scored.append((snippet, score, idx))

    if not scored and _doc_evidence_score(question, doc) >= MIN_EXTRACTIVE_EVIDENCE_SCORE:
        excerpt = _trim_evidence_text(doc.page_content)
        if excerpt:
            scored.append((excerpt, _doc_evidence_score(question, doc), 0))

    scored.sort(key=lambda item: (-item[1], item[2]))
    selected = scored[:max_snippets]
    selected.sort(key=lambda item: item[2])
    return [(snippet, score) for snippet, score, _idx in selected]


def _is_no_data_answer(answer: str) -> bool:
    from spark.retrieval.no_data import HELPFUL_NO_DATA_PREFIX, UNKNOWN_MACHINE_PREFIX

    text = answer.strip()
    return (
        NO_DATA_ANSWER in text
        or UNKNOWN_MACHINE_PREFIX in text
        or HELPFUL_NO_DATA_PREFIX in text
    )


def _order_docs_for_context(question: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """Order context chunks so the most likely source type comes first for the LLM."""
    ranked = sorted(docs, key=lambda d: d.score, reverse=True)
    manual = [d for d in ranked if d.payload.get("document_type") == "machine_manual"]
    sop = [d for d in ranked if d.payload.get("document_type") == "sop"]
    other = [
        d
        for d in ranked
        if d.payload.get("document_type") not in ("machine_manual", "sop")
    ]
    if _is_symptom_action_query(question) and (manual or sop):
        return manual + sop + other
    if sop and _prefers_sop_safety(question):
        return sop + manual + other
    if _manual_preference_allowed(question, docs):
        return manual + sop + other
    return ranked


def _format_extractive_evidence_answer(
    question: str,
    docs: list[RetrievedDoc],
    *,
    max_docs: int = 3,
    max_items: int = 5,
) -> tuple[str, list[RetrievedDoc]] | None:
    ranked_docs = sorted(
        _docs_for_symptom_action_evidence(question, docs),
        key=lambda d: (
            _procedure_doc_rank(d) if _is_symptom_action_query(question) else 0,
            _doc_evidence_score(question, d),
            d.score,
        ),
        reverse=True,
    )
    lines = ["พบข้อมูลที่เกี่ยวข้องจากเอกสาร:"]
    used_docs: list[RetrievedDoc] = []
    seen_texts: set[str] = set()
    seen_sources: set[tuple[Any, ...]] = set()
    item_count = 0

    for doc in ranked_docs[:max_docs]:
        snippets = _evidence_snippets_for_doc(question, doc)
        for snippet, _score in snippets:
            normalized = snippet.lower()
            if normalized in seen_texts:
                continue
            seen_texts.add(normalized)
            lines.append(f"- {_source_label(doc)} {snippet}")
            source_key = _source_identity(doc)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                used_docs.append(doc)
            item_count += 1
            if item_count >= max_items:
                break
        if item_count >= max_items:
            break

    if not used_docs:
        return None
    lines.append("สรุปนี้ยึดตามข้อความที่พบในเอกสารเท่านั้น")
    return "\n".join(lines), used_docs


def _select_sources_for_display(
    docs: list[RetrievedDoc],
    answer: str,
    *,
    question: str = "",
) -> list[RetrievedDoc]:
    """Show only sources the answer actually used — avoids 1.0 noise with a no-data reply."""
    candidates = _docs_for_symptom_action_evidence(question, docs) if question else docs
    def _dedup(selected: list[RetrievedDoc], limit: int = 3) -> list[RetrievedDoc]:
        seen: set[tuple[Any, ...]] = set()
        unique: list[RetrievedDoc] = []
        for doc in selected:
            key = _source_identity(doc)
            if key in seen:
                continue
            seen.add(key)
            unique.append(doc)
            if len(unique) >= limit:
                break
        return unique

    exact: list[RetrievedDoc] = []
    for d in candidates:
        label = _source_label(d)
        bare_label = label.strip("[]")
        if label in answer or bare_label in answer:
            exact.append(d)
    if exact:
        return _dedup(exact)

    weak: list[RetrievedDoc] = []
    for d in candidates:
        sf = d.payload.get("source_file") or ""
        title = d.payload.get("title") or ""
        if (sf and sf in answer) or (title and title in answer):
            weak.append(d)
    if weak:
        return _dedup(sorted(weak, key=lambda d: d.score, reverse=True))
    if NO_DATA_ANSWER in answer:
        return []
    ranked = sorted(candidates, key=lambda d: (_procedure_doc_rank(d), d.score), reverse=True)
    # If the answer did not name a source, expose only the strongest source.
    return ranked[:1]


def _source_label(doc: RetrievedDoc) -> str:
    payload = doc.payload
    name = payload.get("source_file") or payload.get("title") or "เอกสาร"
    page = coerce_source_page(payload.get("page"))
    if page:
        return f"[{name} หน้า {page}]"
    sheet = payload.get("source_sheet")
    row = payload.get("row_number")
    if sheet and row:
        return f"[{name} sheet {sheet} row {row}]"
    if sheet:
        return f"[{name} sheet {sheet}]"
    return f"[{name}]"


def _answer_mentions_any_source(answer: str, docs: list[RetrievedDoc]) -> bool:
    for doc in docs:
        label = _source_label(doc)
        bare_label = label.strip("[]")
        if label in answer or bare_label in answer:
            return True

        payload = doc.payload
        has_locator = any(
            payload.get(key) is not None for key in ("page", "source_sheet", "row_number")
        )
        if has_locator:
            continue

        source_file = doc.payload.get("source_file")
        title = doc.payload.get("title")
        if source_file and source_file in answer:
            return True
        if title and title in answer:
            return True
    return False


def _ensure_answer_citations(answer: str, docs: list[RetrievedDoc]) -> str:
    if not docs or answer in (NO_DATA_ANSWER, UNAVAILABLE_ANSWER):
        return answer
    if _answer_mentions_any_source(answer, docs):
        return answer

    labels: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        label = _source_label(doc)
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
        if len(labels) >= 3:
            break
    if not labels:
        return answer
    return f"{answer.rstrip()}\n\nอ้างอิง: {', '.join(labels)}"


def _build_context(docs: list[RetrievedDoc]) -> str:
    parts: list[str] = []
    for d in docs:
        p = d.payload
        locator = f"หน้า {p.get('page')}" if p.get("page") is not None else ""
        if not locator and p.get("source_sheet"):
            locator = f"sheet {p.get('source_sheet')}"
            if p.get("row_number") is not None:
                locator = f"{locator} row {p.get('row_number')}"
        label = f"[{p.get('source_file', '?')} {locator or '-'} | {p.get('document_type', '')}]"
        parts.append(f"{label}\n{d.page_content}")
    return "\n\n---\n\n".join(parts)
