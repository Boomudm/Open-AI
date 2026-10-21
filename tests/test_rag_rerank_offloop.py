from __future__ import annotations

import pytest

from spark.services.rag_service import RAGService, RetrievedDoc


def _doc(i: int, score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=f"chunk-{i}",
        score=score,
        vector_score=score,
        payload={"chunk_id": f"c{i}", "source_file": "m.pdf", "document_type": "machine_manual"},
    )


def test_cap_keeps_highest_scored_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.rerank.prefilter.settings.rag_rerank_max_candidates", 10)
    docs = [_doc(i, score=i / 100.0) for i in range(100)]

    capped = svc._cap_rerank_candidates(docs, top_k=6)

    assert len(capped) == 10
    # Highest scores retained (chunks 90..99).
    assert {d.payload["chunk_id"] for d in capped} == {f"c{i}" for i in range(90, 100)}


def test_cap_never_trims_below_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.rerank.prefilter.settings.rag_rerank_max_candidates", 5)
    docs = [_doc(i, score=i / 100.0) for i in range(30)]

    capped = svc._cap_rerank_candidates(docs, top_k=20)

    assert len(capped) == 20


def test_cap_noop_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.rerank.prefilter.settings.rag_rerank_max_candidates", 64)
    docs = [_doc(i, score=i / 100.0) for i in range(8)]

    capped = svc._cap_rerank_candidates(docs, top_k=6)

    assert capped is docs


@pytest.mark.asyncio
async def test_async_rerank_offloads_and_matches_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    svc._force_rerank_circuit_degraded = True
    monkeypatch.setattr("spark.retrieval.rerank.prefilter.settings.rag_rerank_max_candidates", 64)
    docs = [_doc(i, score=(i % 7) / 10.0) for i in range(12)]

    sync_result = svc._apply_retrieval_rerank("cooling fan temperature", list(docs), top_k=5)
    async_result = await svc._apply_retrieval_rerank_async(
        "cooling fan temperature", list(docs), top_k=5
    )

    assert [d.payload["chunk_id"] for d in async_result] == [
        d.payload["chunk_id"] for d in sync_result
    ]
    assert len(async_result) <= 5


@pytest.mark.asyncio
async def test_async_rerank_empty_input() -> None:
    svc = RAGService()
    assert await svc._apply_retrieval_rerank_async("q", [], top_k=5) == []
