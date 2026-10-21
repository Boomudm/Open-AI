"""Stable structured-log keys for RAG SLO dashboards — delegates to rag_events schema."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spark.core.rag_events import (
    INGEST_SWAP_COMMITTED_KEYS,
    RAG_ANSWER_PRODUCED_KEYS,
    ingest_generation_from_docs,
    ingest_swap_committed_fields as _ingest_swap_committed_fields,
    rag_answer_produced_fields as _rag_answer_produced_fields,
)

if TYPE_CHECKING:
    from spark.retrieval.models import RetrievedDoc

__all__ = [
    "RAG_ANSWER_PRODUCED_KEYS",
    "INGEST_SWAP_COMMITTED_KEYS",
    "ingest_generation_from_docs",
    "rag_answer_produced_fields",
    "ingest_swap_committed_fields",
]


def rag_answer_produced_fields(
    *,
    answer_path: str,
    retrieval_sources: list[str],
    fallback_level: int,
    top_doc_score: float,
    sources_count: int,
    latency_ms: float,
    question: str,
    safety_intent: str = "none",
    circuit_mode: str = "closed",
    docs: list[RetrievedDoc] | None = None,
) -> dict[str, Any]:
    return _rag_answer_produced_fields(
        answer_path=answer_path,
        retrieval_sources=retrieval_sources,
        fallback_level=fallback_level,
        top_doc_score=top_doc_score,
        sources_count=sources_count,
        latency_ms=latency_ms,
        question=question,
        safety_intent=safety_intent,
        circuit_mode=circuit_mode,
        docs=docs,
    )


def ingest_swap_committed_fields(
    *,
    doc_id: str,
    staging_generation: int,
    replaced_generation: int | None,
    chunks_count: int,
    reason_code: str = "committed",
    factory_id: str | None = None,
    attempt_count: int | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    _ = replaced_generation
    return _ingest_swap_committed_fields(
        doc_id=doc_id,
        ingest_generation=staging_generation,
        chunks_count=chunks_count,
        policy_version=policy_version,
        factory_id=factory_id,
        reason_code=reason_code,
        attempt_count=attempt_count,
    )
