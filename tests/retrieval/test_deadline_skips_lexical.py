"""Phase 11 — cooperative deadline skips lexical leg when budget exhausted."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from spark.core.config import settings
from spark.retrieval.deadline import RequestDeadline
from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.models import RAGFilter, RetrievedDoc


@pytest.mark.asyncio
async def test_retrieve_skips_lexical_when_deadline_near_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rag_lexical_budget_ms", 5_000)
    monkeypatch.setattr(settings, "rag_request_budget_ms", 8_000)

    lexical_called = False

    async def fake_lexical(*_args, **_kwargs):
        nonlocal lexical_called
        lexical_called = True
        return [], False

    vector_doc = RetrievedDoc(
        page_content="Operating pressure 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": "c1"},
    )

    async def fake_vector(*_args, **_kwargs):
        class Result:
            hits = [vector_doc]
            failed_collections = []
            embed_failed = False
            sparse_encoder_id = "none"

        return Result()

    monkeypatch.setattr(
        "spark.retrieval.engine.search_qdrant_hybrid",
        AsyncMock(side_effect=fake_vector),
    )

    engine = RetrievalEngine(embedder=AsyncMock())
    monkeypatch.setattr(engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(engine, "_apply_rerank", None)

    # Avoid Postgres/factory config lookups in tests
    from spark.retrieval.tuning import RagFusionConfig

    async def _no_multi_hop(*_a, **_kw):
        return None

    monkeypatch.setattr(engine, "_retrieve_multi_hop", _no_multi_hop)
    monkeypatch.setattr(engine, "resolve_fusion_config", AsyncMock(return_value=RagFusionConfig.from_factory_config({})))
    monkeypatch.setattr(engine, "resolve_lexical_engine", AsyncMock(return_value="postgres"))
    monkeypatch.setattr(engine, "_rag_circuit_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "spark.retrieval.engine.hydrate_parent_content_from_pg",
        AsyncMock(),
    )

    # 6s elapsed → ~2s remaining, below 5s lexical budget
    started = time.perf_counter() - 6.0
    deadline = RequestDeadline.from_settings(started_at=started)

    docs, report = await engine.retrieve(
        "pressure limit",
        RAGFilter(factory_id="F-01"),
        top_k=4,
        deadline=deadline,
    )

    assert lexical_called is False
    assert len(docs) >= 1
    assert report.lexical_count == 0


@pytest.mark.asyncio
async def test_rerank_pipeline_receives_non_none_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.retrieval.rerank.pipeline import RerankPipeline

    async def fake_score(*_args, **_kwargs):
        return [0.9]

    monkeypatch.setattr(
        "spark.retrieval.rerank.pipeline.cross_encoder.score_pairs_async",
        AsyncMock(side_effect=fake_score),
    )

    pipeline = RerankPipeline()
    deadline = RequestDeadline.from_settings(started_at=time.perf_counter())
    doc = RetrievedDoc(
        page_content="Pressure 5 bar.",
        score=0.5,
        vector_score=0.5,
        payload={"chunk_id": "c1"},
    )

    result = await pipeline.apply(
        "pressure",
        [doc],
        top_k=1,
        session_id="sess-1",
        deadline=deadline,
    )
    assert result.docs
    assert deadline.remaining_ms() >= 0
