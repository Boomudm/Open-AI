"""Redis sliding-window rate limits + factory backpressure (Phase 9)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import HTTPException

from spark.api.platform.rate_limit_lua import increment_sliding_window
from spark.core.cache import Cache
from spark.core.config import settings
from spark.core.metrics import rag_rate_limited_total


async def check_rag_query_rate_limit(
    *,
    user_id: str | None,
    factory_id: str | None,
) -> None:
    user_limit = int(settings.rag_query_rate_limit_per_user_min or 0)
    factory_limit = int(settings.rag_query_rate_limit_per_factory_min or 0)
    if user_limit <= 0 and factory_limit <= 0:
        return

    retry_after = 60
    if user_id and user_limit > 0:
        used = await increment_sliding_window(f"spark:rag:rate:user:{user_id}")
        if used > user_limit:
            rag_rate_limited_total.labels(scope="user").inc()
            raise HTTPException(
                429,
                detail="RAG query rate limit exceeded for user",
                headers={"Retry-After": str(retry_after)},
            )

    if factory_id and factory_limit > 0:
        used = await increment_sliding_window(f"spark:rag:rate:factory:{factory_id}")
        if used > factory_limit:
            rag_rate_limited_total.labels(scope="factory").inc()
            raise HTTPException(
                429,
                detail="RAG query rate limit exceeded for factory",
                headers={"Retry-After": str(retry_after)},
            )


_GLOBAL_INFLIGHT_KEY = "spark:rag:inflight:__global__"


def _at_capacity(scope: str, count: int) -> HTTPException:
    rag_rate_limited_total.labels(scope=scope).inc()
    msg = "System is at capacity — please retry" if scope == "inflight_global" else "Factory query queue full"
    return HTTPException(
        429,
        detail={
            "detail": msg,
            "code": "rag_at_capacity",
            "retryable": True,
            "retry_after_ms": 2000,
            "queue_depth": count,
        },
        headers={"Retry-After": "2"},
    )


async def _incr_with_ttl(cache, key: str, ttl: int) -> int:
    count = await cache.incr(key)
    try:
        await cache.expire(key, ttl)
    except Exception:
        pass
    return count


async def _safe_decr(cache, key: str) -> None:
    try:
        result = await cache.decr(key)
        if isinstance(result, int) and result < 0:
            await cache.set(key, "0")
    except Exception:
        pass


async def acquire_rag_inflight_slot(factory_id: str | None) -> None:
    """Concurrent-RAG backpressure — raises a fast 429 when at capacity.

    Two caps apply: a global cap across all factories (the shared LLM backend)
    and the per-factory cap. The global cap is checked first so a saturated
    backend rejects immediately instead of every request stalling out to the
    request budget and returning "AI unavailable".
    """
    factory_limit = int(getattr(settings, "rag_inflight_max_per_factory", 50) or 0)
    global_limit = int(getattr(settings, "rag_inflight_max_global", 0) or 0)
    ttl = int(getattr(settings, "rag_inflight_ttl_sec", 300))
    cache = Cache.get()

    global_held = False
    if global_limit > 0:
        gcount = await _incr_with_ttl(cache, _GLOBAL_INFLIGHT_KEY, ttl)
        global_held = True
        if gcount > global_limit:
            await _safe_decr(cache, _GLOBAL_INFLIGHT_KEY)
            raise _at_capacity("inflight_global", gcount)

    if factory_id and factory_limit > 0:
        key = f"spark:rag:inflight:{factory_id}"
        count = await _incr_with_ttl(cache, key, ttl)
        if count > factory_limit:
            await _safe_decr(cache, key)
            if global_held:
                await _safe_decr(cache, _GLOBAL_INFLIGHT_KEY)
            raise _at_capacity("inflight", count)


async def release_rag_inflight_slot(factory_id: str | None) -> None:
    factory_limit = int(getattr(settings, "rag_inflight_max_per_factory", 50) or 0)
    global_limit = int(getattr(settings, "rag_inflight_max_global", 0) or 0)
    cache = Cache.get()
    if factory_id and factory_limit > 0:
        await _safe_decr(cache, f"spark:rag:inflight:{factory_id}")
    if global_limit > 0:
        await _safe_decr(cache, _GLOBAL_INFLIGHT_KEY)


@asynccontextmanager
async def rag_inflight_guard(factory_id: str | None) -> AsyncIterator[None]:
    await acquire_rag_inflight_slot(factory_id)
    try:
        yield
    finally:
        await release_rag_inflight_slot(factory_id)
