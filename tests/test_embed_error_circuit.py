"""Embed failure records circuit outcome (remediation v2 Phase 8)."""

from __future__ import annotations

import pytest

from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.vector.qdrant_search import VectorSearchResult
from spark.retrieval.models import RAGFilter
from spark.retrieval.tuning import RagFusionConfig


async def _fusion_config(_rf):
    return RagFusionConfig.from_factory_config({})


async def _lexical_engine(_rf):
    return "postgres_thai_v3"


@pytest.mark.asyncio
async def test_embed_failure_records_circuit_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[str] = []

    async def fake_search(*_args, **_kwargs):
        return VectorSearchResult(hits=[], embed_failed=True, failed_collections=["c1"])

    async def fake_lexical(*_args, **_kwargs):
        return [], False

    async def fake_record(outcome: str, *, enabled: bool, **kwargs) -> None:
        if enabled:
            recorded.append(outcome)

    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_search)
    monkeypatch.setattr(
        "spark.retrieval.safety.circuit_breaker.record_rag_outcome_async",
        fake_record,
    )

    async def _circuit_enabled(_rf):
        return True

    engine = RetrievalEngine(embedder=object())
    monkeypatch.setattr(engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(engine, "resolve_fusion_config", _fusion_config)
    monkeypatch.setattr(engine, "resolve_lexical_engine", _lexical_engine)
    monkeypatch.setattr(engine, "_rag_circuit_enabled", _circuit_enabled)

    await engine.retrieve("LOTO procedure", RAGFilter(factory_id="F-01"), 3)
    assert "embed_error" in recorded
