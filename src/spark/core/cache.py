"""Redis-backed cache helpers.

Production profile (``AppProfile.redis_required``) refuses silent in-memory
fallback — startup and cache operations fail fast when Redis is unreachable.
Test profile retains ``_MemCache`` for unit tests without Redis.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

import redis.asyncio as redis_async

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

_INCR_EXPIRE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisRequiredError(RuntimeError):
    """Raised when Redis is mandatory but unreachable."""


class _MemCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._zsets: dict[str, list[tuple[str, float]]] = {}
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            row = self._store.get(key)
            if not row:
                return None
            expires, value = row
            if expires < time.time():
                self._store.pop(key, None)
                return None
            return value

    async def pop(self, key: str) -> str | None:
        async with self._lock:
            row = self._store.pop(key, None)
            if not row:
                return None
            expires, value = row
            if expires < time.time():
                return None
            return value

    async def setex(self, key: str, ttl: int, value: str) -> None:
        async with self._lock:
            effective_ttl = ttl if ttl > 0 else 86400 * 365
            self._store[key] = (time.time() + effective_ttl, value)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        async with self._lock:
            rows = self._zsets.setdefault(key, [])
            for member, score in mapping.items():
                rows.append((member, score))

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        async with self._lock:
            rows = self._zsets.get(key, [])
            self._zsets[key] = [
                (member, score)
                for member, score in rows
                if not (min_score <= score <= max_score)
            ]

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        async with self._lock:
            rows = self._zsets.get(key, [])
            return [
                member
                for member, score in rows
                if min_score <= score <= max_score
            ]

    async def incr(self, key: str) -> int:
        async with self._lock:
            value = self._counters.get(key, 0) + 1
            self._counters[key] = value
            return value

    async def decr(self, key: str) -> int:
        async with self._lock:
            value = max(0, self._counters.get(key, 0) - 1)
            self._counters[key] = value
            return value


class Cache:
    _instance: "Cache | None" = None

    def __init__(self) -> None:
        self._redis: redis_async.Redis | None = None
        self._mem = _MemCache()
        self._redis_ok: bool | None = None

    @classmethod
    def get(cls) -> "Cache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        """Drop singleton between tests (SPARK_PROFILE=test only)."""
        cls._instance = None

    async def close_for_worker(self) -> None:
        """Close the Redis connection pool after a Celery task completes.

        Each Celery task runs inside asyncio.run(), which creates a new event
        loop per task.  redis.asyncio stores asyncio primitives (Locks, Futures)
        that are bound to the loop in which they were first created.  Reusing
        the same Redis client across different asyncio.run() invocations causes
        ``RuntimeError: Task got Future attached to a different loop`` on the
        second task and beyond.  Closing and clearing the client here forces a
        fresh connection to be created in the next task's event loop.
        """
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            self._redis_ok = None

    def _redis_required(self) -> bool:
        return settings.app_profile.redis_required

    async def ping(self) -> bool:
        """Return True when Redis responds to PING."""
        try:
            if self._redis is None:
                self._redis = redis_async.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_ok = True
            return True
        except Exception as exc:
            log.warning("redis_ping_failed", error=str(exc)[:120])
            self._redis_ok = False
            return False

    async def ensure_ready(self, *, redis_required: bool | None = None) -> None:
        """Startup gate — fail when Redis is required but unreachable."""
        required = self._redis_required() if redis_required is None else redis_required
        if not required:
            return
        if not await self.ping():
            raise RedisRequiredError("Redis required in production profile but unreachable")

    async def _client(self) -> redis_async.Redis | None:
        if self._redis_ok is False:
            if self._redis_required():
                raise RedisRequiredError("Redis required but previously marked unavailable")
            return None
        if self._redis is None:
            self._redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            await self._redis.ping()
            self._redis_ok = True
            return self._redis
        except Exception as exc:
            log.warning("cache_redis_unavailable", error=str(exc)[:120])
            self._redis_ok = False
            if self._redis_required():
                raise RedisRequiredError(
                    f"Redis required in production profile but unavailable: {exc}"
                ) from exc
            log.warning("cache_redis_fallback_mem")
            return None

    async def get_json(self, key: str) -> Any | None:
        client = await self._client()
        raw = await (client.get(key) if client else self._mem.get(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int = 300) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        client = await self._client()
        if client:
            if ttl <= 0:
                await client.set(key, payload)
            else:
                await client.setex(key, ttl, payload)
        else:
            # ttl <= 0 means "no expiry" — use a large TTL for in-memory fallback
            effective_ttl = ttl if ttl > 0 else 86400 * 365
            await self._mem.setex(key, effective_ttl, payload)

    async def atomic_pop_json(self, key: str) -> Any | None:
        """Atomically read and delete a JSON value (GETDEL on Redis)."""
        client = await self._client()
        if client:
            raw = await client.getdel(key)
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        raw = await self._mem.pop(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def pop_json(self, key: str) -> Any | None:
        """Deprecated alias — use :meth:`atomic_pop_json` for one-time secrets."""
        return await self.atomic_pop_json(key)

    async def set(self, key: str, value: str) -> None:
        """Set a key without expiry (or very large TTL for in-memory fallback)."""
        client = await self._client()
        if client:
            await client.set(key, value)
        else:
            await self._mem.setex(key, 86400 * 365, value)

    async def expire(self, key: str, ttl: int) -> None:
        """Set TTL on an existing key."""
        client = await self._client()
        if client:
            await client.expire(key, ttl)
        # In-memory fallback: re-read and re-set with new TTL
        else:
            raw = await self._mem.get(key)
            if raw is not None:
                await self._mem.setex(key, ttl, raw)

    async def delete(self, key: str) -> None:
        client = await self._client()
        if client:
            await client.delete(key)
            return
        await self._mem.pop(key)
        async with self._mem._lock:
            self._mem._zsets.pop(key, None)
            self._mem._counters.pop(key, None)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        client = await self._client()
        if client:
            await client.zadd(key, mapping)
            return
        await self._mem.zadd(key, mapping)

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        client = await self._client()
        if client:
            await client.zremrangebyscore(key, min_score, max_score)
            return
        await self._mem.zremrangebyscore(key, min_score, max_score)

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        client = await self._client()
        if client:
            return await client.zrangebyscore(key, min_score, max_score)
        return await self._mem.zrangebyscore(key, min_score, max_score)

    async def incr(self, key: str) -> int:
        client = await self._client()
        if client:
            return int(await client.incr(key))
        return await self._mem.incr(key)

    async def incr_with_ttl(self, key: str, *, ttl: int, window_sec: int = 60) -> int:
        """Atomic INCR with EXPIRE on first increment (Redis Lua); mem fallback for tests."""
        client = await self._client()
        if client:
            result = await client.eval(_INCR_EXPIRE_SCRIPT, 1, key, str(max(1, window_sec)))
            return int(result)
        count = await self._mem.incr(key)
        await self._mem.setex(f"__ttl__:{key}", ttl, str(count))
        return count

    async def decr(self, key: str) -> int:
        client = await self._client()
        if client:
            return int(await client.decr(key))
        return await self._mem.decr(key)

    async def clear_spark_keys(self) -> int:
        """Delete all keys prefixed with spark: (safe cache purge)."""
        client = await self._client()
        if not client:
            self._mem._store.clear()
            self._mem._zsets.clear()
            self._mem._counters.clear()
            return 0
        deleted = 0
        async for key in client.scan_iter(match="spark:*", count=200):
            await client.delete(key)
            deleted += 1
        return deleted


async def ensure_redis_ready(*, redis_required: bool | None = None) -> None:
    """Convenience wrapper for API startup lifespan."""
    await Cache.get().ensure_ready(redis_required=redis_required)


def cache_key(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return "spark:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()
