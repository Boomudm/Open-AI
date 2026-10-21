"""Semantic NLI grounding gate — LLM-based entailment with lexical fallback (Phase 17).

Remediation v4: negation detection, raised lexical threshold, safety fail-closed.
"""

from __future__ import annotations

import asyncio
import re

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.generation.types import GroundedGenerateResult
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent

log = get_logger(__name__)

_NLI_VERIFY_PROFILE = "tagging"

_NLI_SYSTEM_PROMPT = (
    "You are a strict fact-checker for factory maintenance answers. "
    "Given CONTEXT (retrieved documents) and an ANSWER sentence, determine if "
    "the sentence is SUPPORTED by the context.\n"
    "Reply with exactly one word: SUPPORTED or UNSUPPORTED.\n"
    "Rules:\n"
    "- Numbers, units, part codes must match exactly\n"
    "- Safety procedures must not be invented\n"
    "- Generic connector sentences (เช่น, ดังนั้น, โดยสรุป) are SUPPORTED\n"
    "- If uncertain, say UNSUPPORTED"
)

SAFETY_DOCUMENT_TYPES = frozenset({"sop", "machine_manual", "safety_certificate"})

_NEGATION_TOKENS_EN = frozenset({
    "not", "no", "never", "don't", "doesn't", "shouldn't", "cannot",
    "mustn't", "won't", "isn't", "aren't", "wasn't", "weren't",
    "do not", "does not", "should not", "must not", "will not",
    "can not", "is not", "are not",
})
_NEGATION_TOKENS_TH = frozenset({
    "ไม่", "ห้าม", "อย่า", "ไม่ได้", "ไม่ควร", "ไม่ต้อง",
})
_NEGATION_TOKENS = _NEGATION_TOKENS_EN | _NEGATION_TOKENS_TH

_LEXICAL_OVERLAP_THRESHOLD = 0.45


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip() for part in parts if part.strip()]


def _is_connector_sentence(sentence: str) -> bool:
    connectors = {
        "ดังนั้น", "โดยสรุป", "สรุป", "กล่าวคือ", "in summary",
        "therefore", "in conclusion", "hence",
    }
    lower = sentence.lower().strip()
    if any(lower.startswith(c) for c in connectors):
        return True
    if len(lower) < 15 and not re.search(r"\d", lower):
        return True
    return False


def _extract_negation_set(text: str) -> frozenset[str]:
    """Return which negation tokens appear in text."""
    lower = text.lower()
    return frozenset(tok for tok in _NEGATION_TOKENS if tok in lower)


def _has_negation_inversion(sentence: str, context: str) -> bool:
    """True when sentence and context disagree on negation polarity.

    Catches inversions like 'should not exceed 100°C' → 'should exceed 100°C'.
    """
    sent_negs = _extract_negation_set(sentence)
    ctx_negs = _extract_negation_set(context)

    sent_lower = sentence.lower()
    ctx_lower = context.lower()

    for neg in sent_negs:
        stripped = sent_lower.replace(neg, " ", 1)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        key_phrase = stripped[:60]
        if len(key_phrase) < 8:
            continue
        if key_phrase in ctx_lower:
            window_start = max(0, ctx_lower.index(key_phrase) - len(neg) - 5)
            window_end = min(len(ctx_lower), ctx_lower.index(key_phrase) + len(key_phrase) + 5)
            window = ctx_lower[window_start:window_end]
            if neg not in window:
                return True

    for neg in ctx_negs - sent_negs:
        stripped = ctx_lower.replace(neg, " ", 1)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        for segment_start in range(0, len(stripped), 50):
            key_phrase = stripped[segment_start:segment_start + 60].strip()
            if len(key_phrase) < 8:
                continue
            if key_phrase in sent_lower:
                return True

    return False


def sentence_entailed_by_context(sentence: str, context: str) -> bool:
    """Lexical overlap with negation check — fallback when LLM verification is unavailable."""
    sentence_tokens = {token for token in re.findall(r"[a-zA-Z0-9฀-๿]{3,}", sentence.lower())}
    if not sentence_tokens:
        return True
    context_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", context.lower()))
    overlap = len(sentence_tokens & context_tokens)
    threshold = getattr(settings, "nli_lexical_overlap_threshold", _LEXICAL_OVERLAP_THRESHOLD)
    if overlap / len(sentence_tokens) < threshold:
        return False
    if _has_negation_inversion(sentence, context):
        log.info("nli_negation_inversion_detected", sentence=sentence[:120])
        return False
    return True


async def _llm_verify_sentence(sentence: str, context: str) -> bool:
    """LLM-based semantic entailment check for a single sentence."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from spark.core.llm_client import get_chat_llm

    if _is_connector_sentence(sentence):
        return True

    try:
        llm = get_chat_llm(_NLI_VERIFY_PROFILE)
        messages = [
            SystemMessage(content=_NLI_SYSTEM_PROMPT),
            HumanMessage(content=f"CONTEXT:\n{context[:3000]}\n\nSENTENCE:\n{sentence}"),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=8.0)
        verdict = str(getattr(response, "content", response) or "").strip().upper()
        return "SUPPORTED" in verdict
    except Exception as exc:
        log.warning("nli_llm_verify_failed", error=str(exc)[:200])
        return sentence_entailed_by_context(sentence, context)


async def _verify_sentences_semantic(
    sentences: list[str],
    context: str,
    *,
    max_concurrent: int = 4,
) -> list[str]:
    """Verify sentences using LLM-based NLI, return unsupported ones."""
    non_trivial = [s for s in sentences if not s.startswith("[chunk_id:") and not _is_connector_sentence(s)]
    if not non_trivial:
        return []

    sem = asyncio.Semaphore(max_concurrent)

    async def check(sentence: str) -> tuple[str, bool]:
        async with sem:
            supported = await _llm_verify_sentence(sentence, context)
            return sentence, supported

    results = await asyncio.gather(*(check(s) for s in non_trivial))
    return [sentence for sentence, supported in results if not supported]


def _verify_sentences_lexical(sentences: list[str], context: str) -> list[str]:
    """Fast lexical fallback verification."""
    return [
        sentence
        for sentence in sentences
        if not sentence.startswith("[chunk_id:") and not sentence_entailed_by_context(sentence, context)
    ]


def is_safety_content(question: str, *, document_types: list[str] | None = None) -> bool:
    """True when the query or source docs involve safety-critical content."""
    if document_types and SAFETY_DOCUMENT_TYPES & set(document_types):
        return True
    safety = detect_safety_intent(question)
    return safety.kind != SafetyIntentKind.NONE


async def apply_nli_gate(
    question: str,
    result: GroundedGenerateResult,
    *,
    context: str,
    intent_kind: str = "none",
    document_types: list[str] | None = None,
) -> GroundedGenerateResult:
    """Semantic grounding gate — LLM-based for safety intents, lexical for general.

    If the gate cannot fully verify retrieved content, keep the answer visible
    and mark it unverified so operators can check the attached sources.
    """
    safety = detect_safety_intent(question)
    _is_safety = is_safety_content(question, document_types=document_types)
    _factual_intents = {"alarm_diagnostic", "part_lookup", "procedure"}
    if safety.kind == SafetyIntentKind.NONE and intent_kind not in _factual_intents and not _is_safety:
        return result
    if not result.citations_verified or not result.answer.strip():
        return result

    sentences = _sentences(result.answer)
    if not sentences:
        return result

    use_semantic = getattr(settings, "nli_gate_semantic_enabled", True) and (
        safety.kind != SafetyIntentKind.NONE or _is_safety
    )

    if use_semantic:
        unsupported = await _verify_sentences_semantic(sentences, context)
    else:
        unsupported = _verify_sentences_lexical(sentences, context)

    if not unsupported:
        return result

    log.info(
        "nli_gate_rejected",
        unsupported_count=len(unsupported),
        total_sentences=len(sentences),
        safety_intent=safety.kind.value,
        is_safety_content=_is_safety,
        mode="semantic" if use_semantic else "lexical",
    )

    return GroundedGenerateResult(
        answer=result.answer,
        cited_docs=result.cited_docs,
        answer_path="nli_gate_warning",
        citations_verified=False,
        generation_mode=result.generation_mode,
    )
