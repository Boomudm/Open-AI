"""Phase 5 — single application fusion point per query."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.fusion import fuse_candidates
from spark.retrieval.vector.qdrant_search import VectorSearchResult
from spark.retrieval.models import RAGFilter, RetrievedDoc


def _doc(chunk_id: str, *, vector: float = 0.5) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=f"content-{chunk_id}",
        score=vector,
        vector_score=vector,
        payload={"chunk_id": chunk_id, "retrieval_mode": "vector"},
    )


@pytest.mark.asyncio
async def test_retrieve_fuses_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fuse_calls: list[int] = []
    original_fuse = fuse_candidates

    def counting_fuse(*args, **kwargs):
        fuse_calls.append(len(args[0]) if args else 0)
        return original_fuse(*args, **kwargs)

    vector_doc = _doc("vec")
    lexical_doc = RetrievedDoc(
        page_content="lex",
        score=0.9,
        vector_score=0.0,
        lexical_score=0.9,
        payload={"chunk_id": "lex", "retrieval_mode": "postgres_lexical"},
    )

    async def fake_vector(*_args, **_kwargs):
        return VectorSearchResult(hits=[vector_doc], sparse_encoder_id="bge_m3")

    engine = RetrievalEngine(embedder=AsyncMock())
    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_vector)
    monkeypatch.setattr(
        engine,
        "retrieve_lexical",
        AsyncMock(return_value=([lexical_doc], False)),
    )
    monkeypatch.setattr("spark.retrieval.engine.fuse_candidates", counting_fuse)

    docs, report = await engine.retrieve("test query", RAGFilter(), top_k=5)

    assert len(fuse_calls) == 1
    assert fuse_calls[0] == 2
    assert docs
    assert report.sparse_encoder_id == "bge_m3"
