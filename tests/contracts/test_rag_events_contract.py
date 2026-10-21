"""Contract: Phase 0 structured RAG/ingest event schemas."""

from __future__ import annotations

import pytest

from spark.core.rag_events import (
    INGEST_SWAP_COMMITTED_REQUIRED_KEYS,
    RAG_ANSWER_PRODUCED_KEYS,
    RAG_RETRIEVAL_COMPLETED_KEYS,
    ingest_swap_committed_fields,
    rag_answer_produced_fields,
    rag_retrieval_completed_fields,
)


def test_ingest_swap_committed_fields_schema() -> None:
    payload = ingest_swap_committed_fields(
        doc_id="doc-1",
        ingest_generation=2,
        chunks_count=10,
        policy_version="1",
        factory_id="f-01",
    )
    assert INGEST_SWAP_COMMITTED_REQUIRED_KEYS <= set(payload.keys())


def test_rag_answer_produced_fields_schema() -> None:
    payload = rag_answer_produced_fields(
        answer_path="grounded_llm",
        retrieval_sources=["vector"],
        fallback_level=0,
        top_doc_score=0.8,
        sources_count=2,
        latency_ms=120.5,
        question="test",
        safety_intent="none",
        circuit_mode="closed",
    )
    assert RAG_ANSWER_PRODUCED_KEYS >= set(payload.keys())


def test_rag_retrieval_completed_fields_schema() -> None:
    payload = rag_retrieval_completed_fields(
        degraded=True,
        degraded_reasons=["lexical_failed"],
        vector_candidates=5,
        lexical_candidates=0,
        failed_collections=[],
        latency_ms=45.2,
        factory_id="f-01",
    )
    assert RAG_RETRIEVAL_COMPLETED_KEYS <= set(payload.keys())


def test_ingest_swap_missing_required_key_raises() -> None:
    from spark.core.rag_events import _assert_keys

    with pytest.raises(ValueError, match="missing required keys"):
        _assert_keys({"doc_id": "x"}, INGEST_SWAP_COMMITTED_REQUIRED_KEYS)
