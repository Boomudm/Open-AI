"""Tiered readiness probes — lite (K8s tick), full matrix with cache."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from sqlalchemy import text

from spark.core.cache import Cache
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal, db_pool_snapshot
from spark.core.llm_profile import load_llm_profile
from spark.core.logging import get_logger

log = get_logger(__name__)

READYZ_CACHE_TTL_SEC = 30.0
_readyz_cache_body: dict[str, Any] | None = None
_readyz_cache_at: float = 0.0


def clear_readyz_cache_for_tests() -> None:
    global _readyz_cache_body, _readyz_cache_at
    _readyz_cache_body = None
    _readyz_cache_at = 0.0


def _cache_get() -> dict[str, Any] | None:
    if _readyz_cache_body is None:
        return None
    if (time.monotonic() - _readyz_cache_at) > READYZ_CACHE_TTL_SEC:
        return None
    return _readyz_cache_body


def _cache_set(body: dict[str, Any]) -> None:
    global _readyz_cache_body, _readyz_cache_at
    _readyz_cache_body = body
    _readyz_cache_at = time.monotonic()


async def readyz_lite() -> tuple[dict[str, Any], int]:
    """Redis PING + Postgres SELECT 1 — for frequent health probes."""
    checks: dict[str, dict] = {}
    overall_ok = True

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)[:120]}
        overall_ok = False

    try:
        redis_ok = await Cache.get().ping()
        checks["redis"] = {"ok": redis_ok, "required": settings.app_profile.redis_required}
        if settings.app_profile.redis_required and not redis_ok:
            overall_ok = False
    except Exception as exc:
        checks["redis"] = {
            "ok": False,
            "required": settings.app_profile.redis_required,
            "error": str(exc)[:120],
        }
        if settings.app_profile.redis_required:
            overall_ok = False

    body = {"status": "ready" if overall_ok else "not_ready", "checks": checks, "tier": "lite"}
    return body, 200 if overall_ok else 503


async def readyz_full(*, bypass_cache: bool = False) -> tuple[dict[str, Any], int]:
    if not bypass_cache:
        cached = _cache_get()
        if cached is not None:
            status = 200 if cached.get("status") == "ready" else 503
            return cached, status

    checks: dict[str, dict] = {}
    overall_ok = True

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True, "pool": db_pool_snapshot()}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)[:120]}
        overall_ok = False

    try:
        redis_ok = await Cache.get().ping()
        checks["redis"] = {"ok": redis_ok, "required": settings.app_profile.redis_required}
        if settings.app_profile.redis_required and not redis_ok:
            overall_ok = False
    except Exception as exc:
        checks["redis"] = {
            "ok": False,
            "required": settings.app_profile.redis_required,
            "error": str(exc)[:120],
        }
        if settings.app_profile.redis_required:
            overall_ok = False

    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"http://{settings.qdrant_host}:{settings.qdrant_port}/")
        checks["qdrant"] = {"ok": r.status_code < 500, "status": r.status_code}
    except Exception as exc:
        checks["qdrant"] = {"ok": False, "error": str(exc)[:120]}
        overall_ok = False

    # LLM reachability — profile-aware (remote gateway vs native Ollama) and NON-FATAL.
    # A degraded LLM must never block /readyz: chat fails loudly per-request, but the
    # API and Web UI must still come up. For openai/vllm profiles we probe the gateway
    # /models endpoint with the same WAF user-agent + Bearer key the real client uses.
    try:
        from spark.core.llm_client import openai_gateway_headers

        try:
            profile = load_llm_profile()
        except Exception:
            profile = {}
        provider = str(profile.get("provider", "ollama")).lower()

        if provider in ("openai", "vllm"):
            base = (profile.get("base_url") or settings.ollama_base_url).rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            headers = dict(openai_gateway_headers())
            api_key = profile.get("api_key") or settings.ollama_api_key
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{base}/models", headers=headers)
            checks["llm"] = {
                "ok": r.status_code < 500,
                "provider": provider,
                "endpoint": base,
                "status": r.status_code,
            }
        else:
            async with httpx.AsyncClient(timeout=2.0) as c:
                r = await c.get(f"{settings.ollama_base_url}/api/tags")
            checks["llm"] = {
                "ok": r.status_code < 500,
                "provider": "ollama",
                "endpoint": settings.ollama_base_url,
                "status": r.status_code,
            }
    except Exception as exc:
        # Non-fatal by design — report degraded, do NOT flip overall_ok.
        checks["llm"] = {"ok": False, "degraded": True, "error": str(exc)[:120]}

    try:
        profile = load_llm_profile()
        model_name = str(profile.get("llm_model") or settings.ollama_llm_model)
    except Exception:
        model_name = settings.ollama_llm_model
    checks["llm_profile"] = {
        "ok": settings.llm_profile not in ("demo",),
        "profile": settings.llm_profile,
        "model": model_name,
    }

    from spark.storage import check_storage_health

    checks["storage"] = await asyncio.to_thread(check_storage_health)
    if not checks["storage"].get("ok"):
        overall_ok = False

    from spark.workers.celery_app import check_celery_worker_health

    checks["celery"] = await asyncio.to_thread(check_celery_worker_health)
    if not checks["celery"].get("ok"):
        overall_ok = False

    body = {"status": "ready" if overall_ok else "not_ready", "checks": checks, "tier": "full"}
    if not bypass_cache:
        _cache_set(body)
    return body, 200 if overall_ok else 503
