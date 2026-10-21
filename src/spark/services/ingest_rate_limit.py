"""Redis token-bucket rate limits for ingest uploads (Phase 3)."""

from __future__ import annotations

from fastapi import HTTPException

from spark.core.config import settings
from spark.core.cache import Cache

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local current = tonumber(redis.call('GET', key) or '0')
if current + cost > limit then
  return 0
end
redis.call('INCRBY', key, cost)
if current == 0 then
  redis.call('EXPIRE', key, ttl)
end
return 1
"""


async def _consume_tokens(key: str, *, limit: int, cost: int, ttl_sec: int = 3600) -> bool:
    if limit <= 0:
        return True
    cache = Cache.get()
    client = await cache._client() if hasattr(cache, "_client") else None
    if client is None:
        current = await cache.get_json(key)
        used = int((current or {}).get("count", 0)) if isinstance(current, dict) else 0
        if used + cost > limit:
            return False
        await cache.set_json(key, {"count": used + cost}, ttl=ttl_sec)
        return True
    allowed = await client.eval(_TOKEN_BUCKET_LUA, 1, key, limit, ttl_sec, cost)
    return bool(int(allowed or 0))


async def check_single_file_rate_limit(factory_id: str) -> None:
    limit = int(settings.ingest_single_file_rate_limit_per_hour)
    ok = await _consume_tokens(f"ingest:tb:single:{factory_id}", limit=limit, cost=1)
    if not ok:
        raise HTTPException(429, "single-file ingest rate limit exceeded for factory")


async def check_reingest_rate_limit(factory_id: str) -> None:
    limit = int(getattr(settings, "ingest_reingest_rate_limit_per_hour", settings.ingest_single_file_rate_limit_per_hour))
    ok = await _consume_tokens(f"ingest:tb:reingest:{factory_id}", limit=limit, cost=1)
    if not ok:
        raise HTTPException(429, "re-ingest rate limit exceeded for factory")


async def check_batch_rate_limit(factory_id: str, count: int) -> None:
    limit = int(settings.ingest_batch_rate_limit_per_hour)
    ok = await _consume_tokens(f"ingest:tb:batch:{factory_id}", limit=limit, cost=max(1, count))
    if not ok:
        raise HTTPException(429, "batch rate limit exceeded for factory")
