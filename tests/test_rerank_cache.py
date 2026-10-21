from __future__ import annotations

import pytest

from spark.retrieval.rerank.cache import get_cached_rerank_scores, store_rerank_scores
from spark.services.qa_cache_service import question_hash


@pytest.mark.asyncio
async def test_rerank_score_cache_roundtrip() -> None:
    session_id = "session-abc"
    question = "bearing SKF 6205"
    chunk_id = "chunk-1"
    await store_rerank_scores(session_id, question, {chunk_id: 0.91})
    cached = await get_cached_rerank_scores(session_id, question, [chunk_id])
    assert cached[chunk_id] == pytest.approx(0.91)
    assert question_hash(question)  # stable hash used internally
