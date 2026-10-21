"""Atomic sliding-window rate limit tests (app-layer v2 Phase 1)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from spark.api.platform.rate_limit_lua import increment_sliding_window
from spark.core.cache import Cache


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    Cache.reset_for_tests()
    yield
    Cache.reset_for_tests()


@pytest.mark.asyncio
async def test_concurrent_increments_are_atomic() -> None:
    # Unique key — local Redis may persist counters across test runs.
    key = f"spark:test:atomic:rate:{uuid.uuid4().hex}"

    async def _bump() -> int:
        return await increment_sliding_window(key, window_sec=60)

    results = await asyncio.gather(*[_bump() for _ in range(20)])
    assert len(results) == 20
    assert sorted(results) == list(range(1, 21))


@pytest.mark.asyncio
async def test_burst_allows_limit_plus_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.api.platform.middleware import rate_limit as rate_limit_mod

    monkeypatch.setattr(rate_limit_mod, "global_rate_limit_rpm", lambda: 5)
    monkeypatch.setattr(rate_limit_mod, "global_rate_limit_burst", lambda: 2)
    assert rate_limit_mod.effective_rate_limit_for_class("default") == 7
