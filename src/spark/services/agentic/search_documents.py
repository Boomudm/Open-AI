"""Agentic tool wrapper around rag_service.query()."""

from __future__ import annotations

import time

from spark.services.agentic.types import (
    RBACContext,
    SearchDocumentsResult,
    SearchFilters,
)
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RAGFilter
from spark.services.rag_service import rag_service


def _require_rbac_context(rbac_context: RBACContext | None) -> RBACContext:
    if rbac_context is None:
        raise ValueError("rbac_context is required for search_documents")
    if rbac_context.allowed_doc_ids is not None and len(rbac_context.allowed_doc_ids) == 0:
        raise ValueError("rbac_context.allowed_doc_ids must not be empty")
    return rbac_context


def _normalize_answer_path(raw_path: str) -> str:
    if raw_path in ("no_data", "hallucination_guard"):
        return "no_data"
    if raw_path in (
        "extractive_answer",
        "fast_synthesis",
        "grounded_extractive",
    ):
        return "extractive"
    if raw_path == "grounded_llm":
        return "llm"
    if raw_path.startswith("llm") or raw_path in ("cache", "llm"):
        return "llm"
    return raw_path


def _to_rag_filter(filters: SearchFilters) -> RAGFilter:
    return RAGFilter(
        factory_id=filters.factory_id,
        machine_id=filters.machine_id,
        document_type=filters.document_type,
        language=filters.language,
        only_active=filters.only_active,
        latest_revision_only=filters.latest_revision_only,
    )


async def search_documents(
    query: str,
    filters: SearchFilters,
    rbac_context: RBACContext,
) -> SearchDocumentsResult:
    """Wrap rag_service.query() — preserves retrieval, guardrails, and citations."""
    rbac = _require_rbac_context(rbac_context)
    start = time.perf_counter()
    result = await rag_service.query(
        question=query,
        rf=_to_rag_filter(filters),
        allowed_doc_ids=rbac.allowed_doc_ids,
        synthesis_question=query,
    )
    raw_path = str(result.used_filters.get("answer_path") or result.answer_path or "unknown")
    answer_path = _normalize_answer_path(raw_path)
    relevance_passed = answer_path != "no_data" and NO_DATA_ANSWER not in (result.answer or "")
    return SearchDocumentsResult(
        answer=result.answer,
        sources=list(result.sources or []),
        relevance_passed=relevance_passed,
        answer_path=answer_path,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )
