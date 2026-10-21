"""Single-flight auth state lookup for token freshness checks."""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict

from spark.core.cache import Cache
from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.services.auth_session import get_cached_user_auth_state, token_version_cache_key

log = get_logger(__name__)

_MAX_LOCKS = 10_000
_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()


def _lock_for_user(user_id: uuid.UUID) -> asyncio.Lock:
    key = str(user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    else:
        _locks.move_to_end(key)
    while len(_locks) > _MAX_LOCKS:
        evicted_key, _ = _locks.popitem(last=False)
        log.debug("auth_cache_lock_evicted", user_id=evicted_key)
    return lock


def reset_auth_session_cache_locks_for_tests() -> None:
    _locks.clear()


async def fetch_user_auth_state(user_id: uuid.UUID) -> dict | None:
    cache = Cache.get()
    cached = await cache.get_json(token_version_cache_key(user_id))
    if cached is not None:
        return cached

    lock = _lock_for_user(user_id)
    async with lock:
        cached = await cache.get_json(token_version_cache_key(user_id))
        if cached is not None:
            return cached
        async with AsyncSessionLocal() as session:
            return await get_cached_user_auth_state(session, user_id)
