"""Phase 11 — stream path passes session_id for rerank CE cache."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.retrieval.models import RetrievedDoc
from spark.retrieval.rerank.cross_encoder import RerankCacheContext
from spark.retrieval.rerank.pipeline import RerankPipeline


@pytest.mark.asyncio
async def test_rerank_pipeline_uses_session_scoped_cache_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Operating pressure must stay below 5 bar.",
        score=0.8,
        vector_score=0.8,
        payload={"chunk_id": chunk_id, "ingest_generation": 1},
    )
    seen_contexts: list[RerankCacheContext | None] = []

    async def fake_score(_query, texts, *, cache_context=None):
        seen_contexts.append(cache_context)
        return [0.88 for _ in texts]

    monkeypatch.setattr(
        "spark.retrieval.rerank.pipeline.cross_encoder.score_pairs_async",
        AsyncMock(side_effect=fake_score),
    )

    from spark.core.config import settings
    monkeypatch.setattr(settings, "rag_rerank_enabled", True)

    pipeline = RerankPipeline()
    session_id = f"sess-{uuid.uuid4()}"
    query = "What is the pressure limit?"

    await pipeline.apply(query, [doc], top_k=1, session_id=session_id)
    await pipeline.apply(query, [doc], top_k=1, session_id=session_id)

    assert len(seen_contexts) == 2
    for ctx in seen_contexts:
        assert ctx is not None
        assert ctx.session_id == session_id
        assert ctx.question == query
        assert chunk_id in ctx.chunk_ids
