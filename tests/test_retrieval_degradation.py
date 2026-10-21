"""Retrieval degradation report tests (Phase 7)."""

from __future__ import annotations

import pytest

from spark.retrieval.degradation import build_retrieval_report
from spark.retrieval.models import RAGFilter
from spark.services.rag_service import RAGService, RetrievedDoc


def test_build_retrieval_report_lexical_failed() -> None:
    report = build_retrieval_report(
        intent="general",
        fusion_method="weighted_rrf",
        vector_count=5,
        lexical_count=0,
        failed_collections=[],
        lexical_failed=True,
    )
    assert report.degraded is True
    assert "lexical_failed" in report.degraded_reasons


@pytest.mark.asyncio
async def test_retrieve_sets_degraded_report_on_lexical_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pg_doc = RetrievedDoc(
        page_content="vector hit",
        score=0.8,
        vector_score=0.8,
        payload={"chunk_id": "c1", "retrieval_mode": "vector"},
    )

    from spark.retrieval.vector.qdrant_search import VectorSearchResult

    async def fake_vector(*_args, **_kwargs):
        return VectorSearchResult(hits=[pg_doc])

    async def fake_lexical(*_args, **_kwargs):
        return [], True

    async def passthrough_rerank(_query, docs, _top_k, **kwargs):
        return docs

    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_vector)
    monkeypatch.setattr(svc.retrieval_engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(svc, "_apply_retrieval_rerank_async", passthrough_rerank)

    docs = await svc._retrieve("test", RAGFilter(), 3)
    assert docs
    assert svc._last_retrieval_report is not None
    assert svc._last_retrieval_report["degraded"] is True
    assert "lexical_failed" in svc._last_retrieval_report["degraded_reasons"]
