"""Login brute-force protection (Redis-backed, app-layer Phase 2)."""

from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException, Request, status

from spark.api.platform.trusted_proxy import client_ip
from spark.api.platform.rate_limit_lua import increment_sliding_window
from spark.core.config import settings

_FAIL_DELAY_SEC = 0.05


def _login_limits() -> tuple[int, int, int]:
    profile = settings.app_profile
    if profile.login_max_attempts_per_ip <= 0:
        return 0, 900, 900
    max_failures = max(1, int(getattr(profile, "login_max_failures", 5) or 5))
    window_sec = max(60, int(getattr(profile, "login_failure_window_sec", 900) or 900))
    lockout_sec = max(60, int(getattr(profile, "login_lockout_sec", 900) or 900))
    return max_failures, window_sec, lockout_sec


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "detail": "too many failed login attempts — try again later",
            "code": "login_rate_limited",
            "retryable": True,
        },
        headers={"Retry-After": str(retry_after)},
    )


async def _lockout_remaining(key: str) -> int:
    from spark.core.cache import Cache

    raw = await Cache.get().get_json(key)
    if not isinstance(raw, dict):
        return 0
    until = float(raw.get("until", 0))
    remaining = int(until - time.time())
    return max(0, remaining)


async def _set_lockout(key: str, *, lockout_sec: int) -> None:
    from spark.core.cache import Cache

    await Cache.get().set_json(
        key,
        {"until": time.time() + lockout_sec},
        ttl=lockout_sec,
    )


async def assert_login_allowed(request: Request, *, username: str) -> None:
    max_failures, _window_sec, _lockout_sec = _login_limits()
    if max_failures <= 0:
        return

    ip = client_ip(request)
    user_key = username.strip().lower()[:128]
    for lock_key in (
        f"spark:login:lock:ip:{ip}",
        f"spark:login:lock:user:{user_key}",
    ):
        remaining = await _lockout_remaining(lock_key)
        if remaining > 0:
            raise _rate_limited(remaining)


async def record_login_failure(request: Request, *, username: str) -> None:
    max_failures, window_sec, lockout_sec = _login_limits()
    if max_failures <= 0:
        await asyncio.sleep(_FAIL_DELAY_SEC)
        return

    ip = client_ip(request)
    user_key = username.strip().lower()[:128]
    ip_fails = await increment_sliding_window(
        f"spark:login:fail:ip:{ip}",
        window_sec=window_sec,
    )
    user_fails = await increment_sliding_window(
        f"spark:login:fail:user:{user_key}",
        window_sec=window_sec,
    )
    if ip_fails >= max_failures or user_fails >= max_failures:
        await _set_lockout(f"spark:login:lock:ip:{ip}", lockout_sec=lockout_sec)
        await _set_lockout(f"spark:login:lock:user:{user_key}", lockout_sec=lockout_sec)
    await asyncio.sleep(_FAIL_DELAY_SEC)


async def clear_login_failures(request: Request, *, username: str) -> None:
    from spark.core.cache import Cache

    ip = client_ip(request)
    user_key = username.strip().lower()[:128]
    cache = Cache.get()
    await cache.delete(f"spark:login:lock:ip:{ip}")
    await cache.delete(f"spark:login:lock:user:{user_key}")
