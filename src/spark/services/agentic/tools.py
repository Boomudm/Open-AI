"""Agentic tool registry — parallel execution with per-tool error isolation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from spark.core.logging import get_logger
from spark.services.agentic.query_database import query_database
from spark.services.agentic.search_documents import search_documents
from spark.services.agentic.synthesis import synthesize_agentic
from spark.services.agentic.types import (
    AgenticSynthesisInput,
    DatabaseScope,
    QueryDatabaseResult,
    RBACContext,
    SearchDocumentsResult,
    SearchFilters,
)

log = get_logger(__name__)

ToolCallable = Callable[..., Awaitable[Any]]

TOOL_REGISTRY: dict[str, ToolCallable] = {
    "search_documents": search_documents,
    "query_database": query_database,
}


def _result_summary(tool_name: str, result: Any | None) -> str:
    if result is None:
        return "error"
    if tool_name == "search_documents" and isinstance(result, SearchDocumentsResult):
        return (
            f"answer_path={result.answer_path} "
            f"relevance_passed={result.relevance_passed} "
            f"sources={len(result.sources)}"
        )
    if tool_name == "query_database" and isinstance(result, QueryDatabaseResult):
        return (
            f"rows={result.rows_returned} "
            f"semantic_passed={result.semantic_validation_passed} "
            f"citations={len(result.citation_refs)}"
        )
    return "ok"


async def _run_tool_isolated(
    tool_name: str,
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        result = await coro_factory()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "agentic_tool_complete",
            tool_name=tool_name,
            latency_ms=latency_ms,
            result_summary=_result_summary(tool_name, result),
        )
        return {
            "tool_name": tool_name,
            "latency_ms": latency_ms,
            "result_summary": _result_summary(tool_name, result),
            "error": None,
            "result": result,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        log.warning(
            "agentic_tool_failed",
            tool_name=tool_name,
            latency_ms=latency_ms,
            error=str(exc)[:500],
        )
        return {
            "tool_name": tool_name,
            "latency_ms": latency_ms,
            "result_summary": "error",
            "error": str(exc)[:500],
            "result": None,
        }


async def run_agentic_tools_parallel(
    *,
    query: str,
    filters: SearchFilters,
    scope: DatabaseScope,
    rbac_context: RBACContext,
) -> dict[str, Any]:
    """Run search_documents and query_database in parallel; isolate tool failures."""
    log.info("agentic_tools_start", query=query[:120])

    async def _search() -> SearchDocumentsResult:
        return await search_documents(query, filters, rbac_context)

    async def _sql() -> QueryDatabaseResult:
        return await query_database(query, scope, rbac_context)

    search_outcome, sql_outcome = await asyncio.gather(
        _run_tool_isolated("search_documents", _search),
        _run_tool_isolated("query_database", _sql),
    )
    tool_results = [search_outcome, sql_outcome]
    tools_called = [item["tool_name"] for item in tool_results]
    tool_latency_ms = sum(float(item.get("latency_ms") or 0) for item in tool_results)

    search_result = (
        search_outcome.get("result")
        if not search_outcome.get("error")
        and isinstance(search_outcome.get("result"), SearchDocumentsResult)
        else None
    )
    db_result = (
        sql_outcome.get("result")
        if not sql_outcome.get("error") and isinstance(sql_outcome.get("result"), QueryDatabaseResult)
        else None
    )

    synthesis = await synthesize_agentic(
        AgenticSynthesisInput(
            question=query,
            search_result=search_result,
            db_result=db_result,
            factory_id=filters.factory_id,
            machine_id=filters.machine_id,
        )
    )
    agentic_sources: list[dict[str, Any]] = list(synthesis.sources)
    if not agentic_sources:
        if search_result:
            agentic_sources.extend(search_result.sources)
        if db_result:
            for ref in db_result.citation_refs:
                agentic_sources.append({"source_type": "sql", "citation_ref": ref})

    return {
        "agentic_tools_called": tools_called,
        "agentic_tool_results": tool_results,
        "agentic_sources": agentic_sources,
        "agentic_answer": synthesis.answer,
        "agentic_answer_path": synthesis.answer_path,
        "hallucination_guard_passed": synthesis.hallucination_guard_passed,
        "citations_verified": synthesis.citations_verified,
        "comparator_notes": synthesis.comparator_notes,
        "agentic_synthesis_latency_ms": synthesis.latency_ms,
        "agentic_tool_latency_ms": tool_latency_ms,
        "agentic_latency_ms": round(tool_latency_ms + synthesis.latency_ms, 2),
    }
