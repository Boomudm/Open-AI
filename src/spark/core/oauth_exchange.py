"""One-time OAuth exchange codes — avoid passing JWTs in redirect URLs."""

from __future__ import annotations

import secrets
from typing import Any

from spark.core.cache import Cache

OAUTH_EXCHANGE_TTL_SEC = 60
_KEY_PREFIX = "spark:oauth:exchange:"


async def store_oauth_exchange_payload(payload: dict[str, Any]) -> str:
    code = secrets.token_urlsafe(32)
    await Cache.get().set_json(f"{_KEY_PREFIX}{code}", payload, ttl=OAUTH_EXCHANGE_TTL_SEC)
    return code


async def consume_oauth_exchange_payload(code: str) -> dict[str, Any] | None:
    trimmed = code.strip()
    if not trimmed:
        return None
    data = await Cache.get().atomic_pop_json(f"{_KEY_PREFIX}{trimmed}")
    if not isinstance(data, dict):
        return None
    return data
