"""Answer self-verification with corrective re-retrieval (Self-RAG + CRAG hybrid).

After initial generation, extracts key claims from the answer and verifies them
against retrieved evidence. If verification confidence is low, triggers a
corrective re-retrieval with refined queries and re-generates.

Pipeline: Generate → Extract Claims → Verify → (Re-retrieve if needed) → Re-generate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.generation.types import GroundedGenerateResult
from spark.retrieval.models import RetrievedDoc

log = get_logger(__name__)


def _thai_trigrams(text: str) -> set[str]:
    """Character trigrams over whitespace-stripped Thai runs.

    Thai has no inter-word spaces, but OCR of the source manuals injects spurious
    ones ("ย ื่ น" for "ยื่น"), so word-token overlap between a clean answer and
    an OCR-mangled chunk collapses to ~0 and falsely marks a correct claim
    unsupported. Comparing space-insensitive character trigrams recovers the
    match.
    """
    compact = re.sub(r"\s+", "", text or "")
    runs = re.findall(r"[฀-๿]{3,}", compact)
    grams: set[str] = set()
    for run in runs:
        grams.update(run[i : i + 3] for i in range(len(run) - 2))
    return grams


@dataclass
class VerificationClaim:
    text: str
    supported: bool = False
    evidence_chunk_id: str | None = None


@dataclass
class SelfVerifyResult:
    original_answer: str
    claims: list[VerificationClaim] = field(default_factory=list)
    verification_score: float = 1.0
    needs_correction: bool = False
    correction_queries: list[str] = field(default_factory=list)


def extract_claims(answer: str) -> list[str]:
    """Extract verifiable factual claims from an answer.

    Claims inherit their paragraph's citation: an LLM that cites once at the end
    of a block ("fact A. fact B. [chunk_id:x]") has grounded every sentence in
    that block, so uncited sentences within a cited block get the block's marker
    appended. verify_claim_against_docs then narrows verification to the cited
    chunk instead of falling back to cross-lingually-broken lexical overlap.
    """
    claims: list[str] = []
    for block in re.split(r"\n+", answer or ""):
        block = block.strip()
        if not block:
            continue
        block_markers = list(re.finditer(r"\[chunk_id:[^\]]+\]", block))
        # A trailing citation grounds the text BEFORE it — sentences after the
        # block's last marker must not inherit (an uncited tail stays uncited).
        segments: list[tuple[str, str | None]] = [(block, None)]
        if block_markers:
            last = block_markers[-1]
            segments = [
                (block[: last.end()], last.group(0)),
                (block[last.end():].strip(), None),
            ]
        for segment, block_citation in segments:
            for s in re.split(r"(?<=[.!?])\s+", segment):
                s = s.strip()
                # Skip markdown headings — "## อุณหภูมิ" is a section heading, not a
                # factual claim, but its trigger word ("temperature") would otherwise
                # make it an uncited claim that drags the support ratio down and falsely
                # fails self-verify. Strip leading list markers off real claims.
                if re.match(r"^#{1,6}\s", s):
                    continue
                s = re.sub(r"^[-*•·]\s+", "", s).strip()
                if not s or len(s) < 10:
                    continue
                if s.startswith("[chunk_id:") or s.startswith("อ้างอิง:") or s.lower().startswith(("source:", "sources:")):
                    continue
                # Keep the [chunk_id:...] citation on the claim: verify_claim_against_docs
                # narrows verification to the cited chunk when present. Stripping it here
                # forced every claim onto pure lexical overlap, which structurally fails
                # for a Thai answer grounded in an English manual (near-zero token overlap)
                # and falsely marked correct, cited answers as unsupported.
                s_text = re.sub(r"\[chunk_id:[^\]]+\]", "", s).strip()
                connector_starts = {"ดังนั้น", "โดยสรุป", "สรุป", "therefore", "in summary", "hence"}
                if any(s_text.lower().startswith(c) for c in connector_starts):
                    continue
                has_explicit_citation = "[chunk_id:" in s.lower() or bool(block_citation)
                has_factual_content = bool(
                    re.search(r"\d", s_text) or
                    re.search(r"[A-Z]{2,}-\d+", s_text) or
                    re.search(r"(ต้อง|ควร|ห้าม|should|must|always|never)", s_text, re.IGNORECASE) or
                    re.search(
                        r"(อุณหภูมิ|แรงดัน|ความเร็ว|เดือน|วินาที|ขั้นตอน|"
                        r"temperature|pressure|speed|rpm|bar|psi|months?|seconds?)",
                        s_text,
                        re.IGNORECASE,
                    ) or
                    # A cited substantive sentence is a claim even when it has
                    # no numeric/code trigger ("waterproof", "covers benefits").
                    # Otherwise a fabricated non-numeric statement can pass as
                    # verified simply by wearing a valid chunk citation.
                    (has_explicit_citation and len(s_text) >= 20)
                )
                if has_factual_content:
                    if block_citation and "[chunk_id:" not in s:
                        s = f"{s} {block_citation}"
                    claims.append(s)
    return claims


def verify_claim_against_docs(claim: str, docs: list[RetrievedDoc]) -> VerificationClaim:
    """Verify a single claim against retrieved documents using lexical + semantic overlap."""
    cited_ids = {
        cid.strip().lower()
        for cid in re.findall(r"\[chunk_id:([^\]]+)\]", claim or "", flags=re.IGNORECASE)
    }
    claim_has_valid_citation = False
    if cited_ids:
        cited_docs = [
            doc
            for doc in docs
            if str(doc.payload.get("chunk_id") or "").strip().lower() in cited_ids
        ]
        if cited_docs:
            docs = cited_docs
            claim_has_valid_citation = True

    normalized_claim = re.sub(r"\[chunk_id:[^\]]+\]", "", claim or "", flags=re.IGNORECASE)
    claim_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", normalized_claim.lower()))
    if not claim_tokens:
        return VerificationClaim(text=claim, supported=True)

    numbers_in_claim = set(re.findall(r"\d+(?:\.\d+)?", normalized_claim))
    thermal_claim = (
        bool({"ร้อน", "อุณหภูมิ", "temperature", "temp", "overheat"} & claim_tokens)
        or "ร้อน" in normalized_claim.lower()
        or "อุณหภูมิ" in normalized_claim.lower()
    )

    best_overlap = 0.0
    best_chunk_id = None
    claim_trigrams = _thai_trigrams(normalized_claim)

    for doc in docs:
        content = (doc.page_content or "").lower()
        content_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", content))
        thermal_content = (
            bool({"temperature", "temp", "overheat", "cooling", "fan"} & content_tokens)
            or "°c" in content
        )

        overlap = len(claim_tokens & content_tokens) / max(len(claim_tokens), 1)

        # OCR-robust Thai fallback: space-insensitive char-trigram overlap so a
        # clean Thai answer still matches an OCR-mangled Thai source chunk.
        if claim_trigrams:
            content_trigrams = _thai_trigrams(content)
            if content_trigrams:
                tri_overlap = len(claim_trigrams & content_trigrams) / len(claim_trigrams)
                overlap = max(overlap, tri_overlap)

        if numbers_in_claim:
            content_numbers = set(re.findall(r"\d+(?:\.\d+)?", content))
            number_match = len(numbers_in_claim & content_numbers) / max(len(numbers_in_claim), 1)
            overlap = overlap * 0.6 + number_match * 0.4
            if number_match > 0 and thermal_claim and thermal_content:
                overlap = max(overlap, 0.75)

        if overlap > best_overlap:
            best_overlap = overlap
            best_chunk_id = str(doc.payload.get("chunk_id") or "")

    supported = best_overlap >= 0.30

    # Cross-lingual grounding: a Thai answer over an English manual has near-zero
    # token overlap even when correct, so a claim that cites a chunk actually in
    # the retrieved set is grounded by construction. Accept it — unless its
    # numbers conflict with the cited evidence, which stays a hard fail (guards
    # against a fabricated value wearing a real citation).
    if claim_has_valid_citation and not supported:
        numbers_conflict = False
        if numbers_in_claim:
            cited_numbers: set[str] = set()
            for doc in docs:
                cited_numbers |= set(re.findall(r"\d+(?:\.\d+)?", (doc.page_content or "")))
            if cited_numbers and not (numbers_in_claim & cited_numbers):
                numbers_conflict = True
        claim_has_thai = bool(re.search(r"[\u0E00-\u0E7F]", normalized_claim))
        cited_has_thai = any(
            re.search(r"[\u0E00-\u0E7F]", doc.page_content or "")
            for doc in docs
        )
        cross_lingual_thai_answer = claim_has_thai and not cited_has_thai
        # Citation-only credit is a UX escape hatch for Thai answers grounded in
        # English manuals, where lexical overlap is structurally near zero. Do
        # not use it for same-language non-numeric claims: those should earn
        # support from the cited text, or remain flagged for user review.
        if not numbers_conflict and (cross_lingual_thai_answer or bool(numbers_in_claim)):
            supported = True
            best_chunk_id = best_chunk_id or next(
                (str(d.payload.get("chunk_id") or "") for d in docs), None
            )

    return VerificationClaim(
        text=claim,
        supported=supported,
        evidence_chunk_id=best_chunk_id if supported else None,
    )


def generate_correction_queries(
    question: str,
    unsupported_claims: list[VerificationClaim],
) -> list[str]:
    """Generate refined queries targeting unsupported claims."""
    queries: list[str] = []
    for claim in unsupported_claims[:3]:
        numbers = re.findall(r"\d+(?:\.\d+)?", claim.text)
        technical_terms = re.findall(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*|[A-Z]{2,}-?\d*", claim.text)

        if technical_terms:
            queries.append(f"{' '.join(technical_terms[:3])} {' '.join(numbers[:2])}")
        else:
            words = claim.text.split()[:8]
            queries.append(" ".join(words))
    return queries


async def self_verify_answer(
    question: str,
    result: GroundedGenerateResult,
    docs: list[RetrievedDoc],
) -> SelfVerifyResult:
    """Verify generated answer claims against retrieved evidence.

    Returns SelfVerifyResult with verification score and optional correction queries.
    """
    answer = result.answer or ""
    claims = extract_claims(answer)

    if not claims:
        return SelfVerifyResult(
            original_answer=answer,
            verification_score=1.0,
            needs_correction=False,
        )

    verified_claims: list[VerificationClaim] = []
    for claim_text in claims:
        vc = verify_claim_against_docs(claim_text, docs)
        verified_claims.append(vc)

    supported_count = sum(1 for c in verified_claims if c.supported)
    total = len(verified_claims)
    score = supported_count / max(total, 1)

    unsupported = [c for c in verified_claims if not c.supported]

    from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent

    safety = detect_safety_intent(question)
    _is_safety = safety.kind != SafetyIntentKind.NONE

    safety_score_threshold = getattr(settings, "self_verify_safety_score_threshold", 0.85)
    safety_max_unsupported = getattr(settings, "self_verify_safety_max_unsupported", 0)
    general_score_threshold = getattr(settings, "self_verify_general_score_threshold", 0.6)
    general_min_unsupported = getattr(settings, "self_verify_general_min_unsupported", 2)

    if _is_safety:
        needs_correction = score < safety_score_threshold or len(unsupported) > safety_max_unsupported
    else:
        needs_correction = score < general_score_threshold and len(unsupported) >= general_min_unsupported

    correction_queries: list[str] = []
    if needs_correction:
        correction_queries = generate_correction_queries(question, unsupported)

    log.info(
        "self_verify_complete",
        total_claims=total,
        supported=supported_count,
        unsupported=len(unsupported),
        score=round(score, 3),
        needs_correction=needs_correction,
        is_safety_content=_is_safety,
        threshold_used="safety" if _is_safety else "general",
    )

    return SelfVerifyResult(
        original_answer=answer,
        claims=verified_claims,
        verification_score=round(score, 4),
        needs_correction=needs_correction,
        correction_queries=correction_queries,
    )
