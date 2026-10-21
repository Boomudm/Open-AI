"""App-layer Redis required startup (Phase 11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from spark.core.app_profile import AppProfile
from spark.core.cache import Cache, RedisRequiredError, ensure_redis_ready


@pytest.mark.asyncio
async def test_ensure_redis_ready_fails_when_required_and_down() -> None:
    Cache.reset_for_tests()
    cache = Cache.get()
    with patch.object(cache, "ping", new=AsyncMock(return_value=False)):
        with pytest.raises(RedisRequiredError, match="Redis required"):
            await cache.ensure_ready(redis_required=True)


@pytest.mark.asyncio
async def test_ensure_redis_ready_ok_when_not_required() -> None:
    Cache.reset_for_tests()
    cache = Cache.get()
    with patch.object(cache, "ping", new=AsyncMock(return_value=False)):
        await cache.ensure_ready(redis_required=False)


@pytest.mark.asyncio
async def test_production_profile_requires_redis_at_startup() -> None:
    profile = AppProfile.for_env(app_env="production", spark_profile="production")
    assert profile.redis_required is True
    Cache.reset_for_tests()
    with patch("spark.core.cache.Cache.get") as get_cache:
        mock = Cache()
        get_cache.return_value = mock
        with patch.object(mock, "ping", new=AsyncMock(return_value=False)):
            with pytest.raises(RedisRequiredError):
                await ensure_redis_ready(redis_required=profile.redis_required)


@pytest.mark.asyncio
async def test_test_profile_allows_mem_fallback_without_redis() -> None:
    profile = AppProfile.for_env(app_env="development", spark_profile="test")
    assert profile.redis_required is False
    Cache.reset_for_tests()
    cache = Cache.get()
    with patch.object(cache, "ping", new=AsyncMock(return_value=False)):
        await ensure_redis_ready(redis_required=profile.redis_required)
    value = await cache.get_json("spark:test:missing")
    assert value is None
