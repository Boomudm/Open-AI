"""Atomic Redis sliding-window counters (Lua INCR + EXPIRE)."""

from __future__ import annotations

import time

from spark.core.cache import Cache

_INCR_EXPIRE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def atomic_sliding_window_increment(key: str, *, window_sec: int = 60) -> int:
    """Atomically increment a fixed-window counter; returns count after increment."""
    cache = Cache.get()
    bucket = int(time.time() // window_sec)
    bucket_key = f"{key}:{bucket}"
    ttl = max(1, int(window_sec) * 2)
    return await cache.incr_with_ttl(bucket_key, ttl=ttl, window_sec=window_sec)


async def increment_sliding_window(key: str, *, window_sec: int = 60) -> int:
    """Public alias for platform rate limits (v2 Phase 1)."""
    return await atomic_sliding_window_increment(key, window_sec=window_sec)
