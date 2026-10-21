"""Stable structured-log event schemas for RAG and ingest observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spark.retrieval.models import RetrievedDoc

INGEST_SWAP_COMMITTED_KEYS: frozenset[str] = frozenset(
    {
        "doc_id",
        "ingest_generation",
        "chunks_count",
        "policy_version",
        "factory_id",
        "reason_code",
        "attempt_count",
    }
)

INGEST_SWAP_COMMITTED_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "doc_id",
        "ingest_generation",
        "chunks_count",
        "policy_version",
        "reason_code",
    }
)

RAG_RETRIEVAL_COMPLETED_KEYS: frozenset[str] = frozenset(
    {
        "degraded",
        "degraded_reasons",
        "vector_candidates",
        "lexical_candidates",
        "failed_collections",
        "factory_id",
        "latency_ms",
    }
)

RAG_ANSWER_PRODUCED_KEYS: frozenset[str] = frozenset(
    {
        "answer_path",
        "fallback_level",
        "safety_intent",
        "circuit_mode",
        "retrieval_sources",
        "ingest_generation",
        "top_doc_score",
        "sources_count",
        "latency_ms",
        "question",
    }
)

RAG_ANSWER_PRODUCED_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "answer_path",
        "fallback_level",
        "safety_intent",
        "circuit_mode",
        "retrieval_sources",
        "top_doc_score",
        "sources_count",
        "latency_ms",
        "question",
    }
)


def _assert_keys(payload: dict[str, Any], required: frozenset[str]) -> dict[str, Any]:
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"event payload missing required keys: {sorted(missing)}")
    return payload


def ingest_generation_from_docs(docs: list[RetrievedDoc]) -> int | None:
    """Primary ingest generation observed on retrieved chunks (max when mixed)."""
    generations: list[int] = []
    for doc in docs:
        raw = doc.payload.get("ingest_generation")
        if raw is None:
            continue
        try:
            generations.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not generations:
        return None
    return max(generations)


def ingest_swap_committed_fields(
    *,
    doc_id: str,
    ingest_generation: int,
    chunks_count: int,
    policy_version: str | None = None,
    factory_id: str | None = None,
    reason_code: str = "committed",
    attempt_count: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "doc_id": doc_id,
        "ingest_generation": ingest_generation,
        "chunks_count": chunks_count,
        "policy_version": policy_version or "none",
        "reason_code": reason_code,
    }
    if factory_id:
        payload["factory_id"] = factory_id
    if attempt_count is not None:
        payload["attempt_count"] = attempt_count
    return _assert_keys(payload, INGEST_SWAP_COMMITTED_REQUIRED_KEYS)


def rag_retrieval_completed_fields(
    *,
    degraded: bool,
    degraded_reasons: list[str],
    vector_candidates: int,
    lexical_candidates: int,
    failed_collections: list[str],
    latency_ms: float,
    factory_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "degraded": degraded,
        "degraded_reasons": degraded_reasons,
        "vector_candidates": vector_candidates,
        "lexical_candidates": lexical_candidates,
        "failed_collections": failed_collections,
        "latency_ms": round(latency_ms, 2),
    }
    if factory_id:
        payload["factory_id"] = factory_id
    return _assert_keys(payload, RAG_RETRIEVAL_COMPLETED_KEYS)


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
    payload: dict[str, Any] = {
        "answer_path": answer_path,
        "fallback_level": fallback_level,
        "safety_intent": safety_intent,
        "circuit_mode": circuit_mode,
        "retrieval_sources": retrieval_sources,
        "top_doc_score": round(top_doc_score, 4),
        "sources_count": sources_count,
        "latency_ms": round(latency_ms, 2),
        "question": question[:120],
    }
    if docs is not None:
        generation = ingest_generation_from_docs(docs)
        if generation is not None:
            payload["ingest_generation"] = generation
    return _assert_keys(payload, RAG_ANSWER_PRODUCED_REQUIRED_KEYS)
