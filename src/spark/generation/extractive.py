"""Extractive-first generation path (Phase 10)."""

from __future__ import annotations

import re

from spark.core.logging import get_logger
from spark.generation.citations import validate_grounded_citations
from spark.generation.context import append_readable_citations
from spark.generation.evidence_spans import (
    EvidenceSpan,
    format_extractive_with_citations,
    select_evidence_spans,
    spans_cover_question,
    validate_spans_grounded,
)
from spark.generation.paraphrase import paraphrase_locked_spans
from spark.generation.thai_enforce import (
    answer_fails_thai_policy,
    question_prefers_thai_output,
    span_text_fails_thai_policy,
)
from spark.generation.types import GenerationInput, GroundedGenerateResult
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.synthesis import _thai_ratio
from spark.generation.translation import translate_for_operator

log = get_logger(__name__)


_MD_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def _is_table_like_span(text: str) -> bool:
    """Markdown-table spans stay untranslated: cell-by-cell translation by a
    small model shreds the row structure ("| 3.6.9 Speed | Monitoin | ใน T |
    1 |") — the chat UI renders the original English table far more readably."""
    return len(_MD_TABLE_LINE_RE.findall(text or "")) >= 2


async def _translate_spans(spans: list[EvidenceSpan]) -> list[EvidenceSpan]:
    import asyncio

    async def _maybe_translate(span: EvidenceSpan) -> str:
        if _is_table_like_span(span.text):
            return span.text
        return await translate_for_operator(span.text)

    texts = await asyncio.gather(*(_maybe_translate(span) for span in spans))
    return [
        EvidenceSpan(
            chunk_id=span.chunk_id,
            text=text,
            doc=span.doc,
            score=span.score,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
        )
        for span, text in zip(spans, texts)
    ]


def _spans_need_translation(question: str, spans: list[EvidenceSpan]) -> bool:
    if not question_prefers_thai_output(question):
        return False
    return any(_thai_ratio(span.text) < 0.12 for span in spans)


def _user_needs_paraphrase(question: str, spans: list[EvidenceSpan]) -> bool:
    if not question_prefers_thai_output(question):
        return False
    return len(spans) > 1 and all(_thai_ratio(span.text) >= 0.12 for span in spans)


def _allow_cross_lingual_extractive(question: str, spans: list[EvidenceSpan], *, translation_attempted: bool) -> bool:
    """English manual spans are acceptable when the operator asked in Thai."""
    if not question_prefers_thai_output(question):
        return False
    if translation_attempted:
        return True
    return bool(spans) and all(_thai_ratio(span.text) < 0.12 for span in spans)


async def format_extractive_answer(
    question: str,
    docs: list[RetrievedDoc],
    *,
    translate: bool = True,
) -> tuple[str, list[RetrievedDoc]] | None:
    spans = select_evidence_spans(question, docs)
    validated = validate_spans_grounded(spans, docs)
    if not validated:
        return None
    translation_attempted = False
    if translate and _spans_need_translation(question, validated):
        translation_attempted = True
        validated = await _translate_spans(validated)
    cross_lingual_ok = _allow_cross_lingual_extractive(
        question, validated, translation_attempted=translation_attempted
    )
    if any(span_text_fails_thai_policy(question, span.text) for span in validated):
        if not cross_lingual_ok:
            return None
    answer, cited_docs = format_extractive_with_citations(validated)
    if answer_fails_thai_policy(question, answer) and not cross_lingual_ok:
        return None
    return answer, cited_docs


async def extractive_answer_from_spans(
    inp: GenerationInput,
    spans: list[EvidenceSpan],
) -> GroundedGenerateResult:
    working = list(spans)
    translation_attempted = False
    if _spans_need_translation(inp.question, working):
        translation_attempted = True
        working = await _translate_spans(working)
    cross_lingual_ok = _allow_cross_lingual_extractive(
        inp.question, working, translation_attempted=translation_attempted
    )
    if any(span_text_fails_thai_policy(inp.question, span.text) for span in working):
        if not cross_lingual_ok:
            return GroundedGenerateResult(
                answer=NO_DATA_ANSWER,
                cited_docs=[],
                answer_path="no_data",
                citations_verified=False,
                generation_mode="no_data",
            )

    if _user_needs_paraphrase(inp.question, working):
        answer = await paraphrase_locked_spans(inp.llm, inp.question, working)
        valid, cited_docs = validate_grounded_citations(answer, inp.docs)
        if valid and not answer_fails_thai_policy(inp.question, answer):
            return GroundedGenerateResult(
                answer=append_readable_citations(answer, cited_docs),
                cited_docs=cited_docs,
                answer_path="grounded_paraphrase",
                citations_verified=True,
                generation_mode="paraphrase",
            )

    answer, cited_docs = format_extractive_with_citations(working)
    if answer_fails_thai_policy(inp.question, answer) and not cross_lingual_ok:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    valid, validated_docs = validate_grounded_citations(answer, inp.docs)
    if not valid:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    return GroundedGenerateResult(
        answer=append_readable_citations(answer, validated_docs),
        cited_docs=validated_docs,
        answer_path="grounded_extractive",
        citations_verified=True,
        generation_mode="extractive",
    )


async def run_extractive_first(inp: GenerationInput) -> GroundedGenerateResult:
    spans = select_evidence_spans(inp.question, inp.docs)
    validated = validate_spans_grounded(spans, inp.docs)
    if not spans_cover_question(validated):
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    return await extractive_answer_from_spans(inp, validated)


async def finalize_extractive(
    question: str,
    docs: list[RetrievedDoc],
    *,
    answer_path: str = "grounded_extractive",
    translate: bool = True,
) -> GroundedGenerateResult:
    extractive = await format_extractive_answer(question, docs, translate=translate)
    if not extractive:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    extractive_answer, cited_docs = extractive
    valid, validated_docs = validate_grounded_citations(extractive_answer, docs)
    if not valid:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    return GroundedGenerateResult(
        answer=append_readable_citations(extractive_answer, validated_docs),
        cited_docs=validated_docs,
        answer_path=answer_path,
        citations_verified=True,
        generation_mode="extractive",
    )
