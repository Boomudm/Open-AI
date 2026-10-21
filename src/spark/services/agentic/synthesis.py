"""Agentic synthesis — merge RAG + SQL tool results under the unified grounded contract."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from spark.core.config import settings
from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger
from spark.schemas.rag import coerce_source_page
from spark.services.agentic.prompts import (
    AGENTIC_SYNTHESIS_SYSTEM,
    build_synthesis_human_prompt,
)
from spark.services.agentic.types import (
    AgenticSynthesisInput,
    AgenticSynthesisOutput,
    QueryDatabaseResult,
    SearchDocumentsResult,
)
from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER
from spark.generation.citations import CHUNK_CITATION_RE
from spark.retrieval.synthesis import (
    _answer_has_hallucinated_numbers,
    _answer_too_english_for_thai_question,
)

log = get_logger(__name__)

_BRACKET_CITATION_RE = re.compile(r"\[[^\]]+\]")


def _has_rag_data(result: SearchDocumentsResult | None) -> bool:
    if result is None:
        return False
    answer = (result.answer or "").strip()
    if not answer or NO_DATA_ANSWER in answer or UNAVAILABLE_ANSWER in answer:
        return False
    return result.relevance_passed or result.answer_path not in ("no_data", "unknown")


def _has_sql_data(result: QueryDatabaseResult | None) -> bool:
    if result is None:
        return False
    answer = (result.answer or "").strip()
    if not answer or NO_DATA_ANSWER in answer or UNAVAILABLE_ANSWER in answer:
        return False
    return result.rows_returned > 0 or result.semantic_validation_passed


def _rag_is_grounded(result: SearchDocumentsResult) -> bool:
    answer = result.answer or ""
    if CHUNK_CITATION_RE.search(answer):
        return True
    if result.answer_path in ("grounded_llm", "grounded_extractive", "extractive"):
        return _answer_has_bracket_citations(answer)
    return False


def _combined_tool_context(
    search_result: SearchDocumentsResult | None,
    db_result: QueryDatabaseResult | None,
    *,
    factory_id: str | None = None,
    machine_id: str | None = None,
) -> str:
    parts: list[str] = []
    if factory_id:
        parts.append(str(factory_id))
    if machine_id:
        parts.append(str(machine_id))
    if search_result and search_result.answer:
        parts.append(search_result.answer)
    if db_result and db_result.answer:
        parts.append(db_result.answer)
    return "\n\n".join(parts)


def _source_label_from_dict(source: dict[str, Any]) -> str:
    name = source.get("source_file") or source.get("title") or "เอกสาร"
    page = coerce_source_page(source.get("page"))
    if page:
        return f"[{name} หน้า {page}]"
    sheet = source.get("source_sheet")
    row = source.get("row_number")
    if sheet and row is not None:
        return f"[{name} sheet {sheet} row {row}]"
    if sheet:
        return f"[{name} sheet {sheet}]"
    return f"[{name}]"


def _merge_sources(
    search_result: SearchDocumentsResult | None,
    db_result: QueryDatabaseResult | None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    if search_result:
        merged.extend(list(search_result.sources or []))
    if db_result:
        for ref in db_result.citation_refs or []:
            merged.append({"source_type": "sql", "citation_ref": ref})
    return merged


def _collect_citation_labels(sources: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if source.get("citation_ref"):
            label = str(source["citation_ref"])
        else:
            label = _source_label_from_dict(source)
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _answer_has_bracket_citations(answer: str) -> bool:
    if CHUNK_CITATION_RE.search(answer or ""):
        return True
    return bool(_BRACKET_CITATION_RE.search(answer or ""))


def _ensure_merged_citations(answer: str, sources: list[dict[str, Any]]) -> tuple[str, bool]:
    labels = _collect_citation_labels(sources)
    if not labels:
        return answer, False
    if _answer_has_bracket_citations(answer):
        mentioned = any(label in answer or label.strip("[]") in answer for label in labels)
        return answer, mentioned
    top = labels[:3]
    return f"{answer.rstrip()}\n\nอ้างอิง: {', '.join(top)}", True


async def _invoke_synthesis_llm(question: str, rag_context: str, sql_context: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_chat_llm()
    human = build_synthesis_human_prompt(
        question=question,
        rag_context=rag_context,
        sql_context=sql_context,
    )
    messages = [SystemMessage(content=AGENTIC_SYNTHESIS_SYSTEM), HumanMessage(content=human)]
    timeout = float(getattr(settings, "rag_llm_timeout_sec", 60.0) or 60.0)
    response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
    content = getattr(response, "content", response)
    return str(content or "").strip()


def _finalize_output(
    *,
    inp: AgenticSynthesisInput,
    answer: str,
    answer_path: str,
    sources: list[dict[str, Any]],
    tool_context: str,
    latency_ms: float,
    comparator_notes: str | None = None,
    skip_hallucination_check: bool = False,
) -> AgenticSynthesisOutput:
    notes = comparator_notes
    if _answer_too_english_for_thai_question(inp.question, answer):
        log.warning("agentic_synthesis_non_thai_answer", question=inp.question[:120])
        notes = (notes + "; " if notes else "") + "non_thai_answer"

    answer_for_number_check = CHUNK_CITATION_RE.sub("", answer)
    answer_for_number_check = _BRACKET_CITATION_RE.sub("", answer_for_number_check)
    if not skip_hallucination_check and _answer_has_hallucinated_numbers(
        answer_for_number_check, tool_context
    ):
        return AgenticSynthesisOutput(
            answer=NO_DATA_ANSWER,
            sources=sources,
            answer_path="no_data",
            citations_verified=False,
            hallucination_guard_passed=False,
            latency_ms=latency_ms,
            comparator_notes=notes,
        )

    cited_answer, citations_verified = _ensure_merged_citations(answer, sources)
    return AgenticSynthesisOutput(
        answer=cited_answer,
        sources=sources,
        answer_path=answer_path,
        citations_verified=citations_verified and _answer_has_bracket_citations(cited_answer),
        hallucination_guard_passed=True,
        latency_ms=latency_ms,
        comparator_notes=notes,
    )


async def synthesize_agentic(inp: AgenticSynthesisInput) -> AgenticSynthesisOutput:
    """Merge tool outputs — RAG answers already grounded by rag_service.query()."""
    start = time.perf_counter()
    rag_data = _has_rag_data(inp.search_result)
    sql_data = _has_sql_data(inp.db_result)
    sources = _merge_sources(inp.search_result, inp.db_result)
    tool_context = _combined_tool_context(
        inp.search_result,
        inp.db_result,
        factory_id=inp.factory_id,
        machine_id=inp.machine_id,
    )

    def _elapsed() -> float:
        return round((time.perf_counter() - start) * 1000, 2)

    if not rag_data and not sql_data:
        return AgenticSynthesisOutput(
            answer=NO_DATA_ANSWER,
            sources=[],
            answer_path="no_data",
            citations_verified=False,
            hallucination_guard_passed=True,
            latency_ms=_elapsed(),
        )

    if rag_data and not sql_data:
        assert inp.search_result is not None
        if _rag_is_grounded(inp.search_result):
            return _finalize_output(
                inp=inp,
                answer=inp.search_result.answer,
                answer_path="rag_only",
                sources=sources,
                tool_context=tool_context,
                latency_ms=_elapsed(),
            )
        return AgenticSynthesisOutput(
            answer=NO_DATA_ANSWER,
            sources=sources,
            answer_path="no_data",
            citations_verified=False,
            hallucination_guard_passed=True,
            latency_ms=_elapsed(),
        )

    if sql_data and not rag_data:
        assert inp.db_result is not None
        return _finalize_output(
            inp=inp,
            answer=inp.db_result.answer,
            answer_path="sql_only",
            sources=sources,
            tool_context=tool_context,
            latency_ms=_elapsed(),
            skip_hallucination_check=False,
        )

    assert inp.search_result is not None and inp.db_result is not None
    if not _rag_is_grounded(inp.search_result):
        return AgenticSynthesisOutput(
            answer=NO_DATA_ANSWER,
            sources=sources,
            answer_path="no_data",
            citations_verified=False,
            hallucination_guard_passed=True,
            latency_ms=_elapsed(),
        )
    try:
        llm_answer = await _invoke_synthesis_llm(
            inp.question,
            rag_context=inp.search_result.answer,
            sql_context=inp.db_result.answer,
        )
        return _finalize_output(
            inp=inp,
            answer=llm_answer,
            answer_path="rag_sql",
            sources=sources,
            tool_context=tool_context,
            latency_ms=_elapsed(),
        )
    except Exception as exc:
        log.warning("agentic_synthesis_failed", case="rag_sql", error=str(exc)[:500])
        return AgenticSynthesisOutput(
            answer=NO_DATA_ANSWER,
            sources=sources,
            answer_path="synthesis_failed",
            citations_verified=False,
            hallucination_guard_passed=True,
            latency_ms=_elapsed(),
        )
