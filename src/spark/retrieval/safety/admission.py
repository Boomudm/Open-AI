"""Unified RAG admission — rate limit + per-factory inflight backpressure (Phase 8)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from spark.retrieval.safety.rate_limit import check_rag_query_rate_limit, rag_inflight_guard


@asynccontextmanager
async def rag_admission_guard(
    factory_id: str | None,
    *,
    user_id: str | None = None,
) -> AsyncIterator[None]:
    """Token bucket + factory-scoped inflight semaphore for all RAG entrypoints."""
    await check_rag_query_rate_limit(user_id=user_id, factory_id=factory_id)
    async with rag_inflight_guard(factory_id):
        yield
