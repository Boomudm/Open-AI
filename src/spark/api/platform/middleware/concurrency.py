"""Dual-plane per-worker in-flight caps (app-layer v2 Phase 1, pure ASGI)."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from spark.api.platform.errors import api_error_response
from spark.api.platform.middleware.admission import (
    AdmissionPlane,
    resolve_admission_plane_for_scope,
)
from spark.api.platform.route_policy import resolve_route_policy
from spark.core.config import settings
from spark.core.metrics import http_admission_rejected_total, http_inflight_gauge

_transactional_sem: asyncio.Semaphore | None = None
_sse_sem: asyncio.Semaphore | None = None
_transactional_limit: int = -1
_sse_limit: int = -1


def _transactional_limit_value() -> int:
    profile = settings.app_profile
    configured = int(settings.http_max_inflight_per_worker or 0)
    return int(profile.transactional_max_inflight_per_worker or configured or 0)


def _sse_limit_value() -> int:
    return int(settings.app_profile.sse_max_inflight_per_worker or 0)


def _semaphore_for_plane(plane: AdmissionPlane) -> asyncio.Semaphore | None:
    global _transactional_sem, _sse_sem, _transactional_limit, _sse_limit
    if plane == "exempt":
        return None
    if plane == "sse":
        limit = _sse_limit_value()
        if limit <= 0:
            return None
        if _sse_sem is None or _sse_limit != limit:
            _sse_sem = asyncio.Semaphore(limit)
            _sse_limit = limit
        return _sse_sem
    limit = _transactional_limit_value()
    if limit <= 0:
        return None
    if _transactional_sem is None or _transactional_limit != limit:
        _transactional_sem = asyncio.Semaphore(limit)
        _transactional_limit = limit
    return _transactional_sem


def reset_concurrency_semaphores_for_tests() -> None:
    """Drop cached semaphores between tests."""
    global _transactional_sem, _sse_sem, _transactional_limit, _sse_limit
    _transactional_sem = None
    _sse_sem = None
    _transactional_limit = -1
    _sse_limit = -1


class ConcurrencyLimitMiddleware:
    """Acquire transactional or SSE semaphore — never both; SSE never uses transactional pool."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        policy = resolve_route_policy(method, path)
        if policy.concurrency_exempt:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        plane, receive = await resolve_admission_plane_for_scope(method, path, request, receive)

        if plane == "exempt":
            await self.app(scope, receive, send)
            return

        sem = _semaphore_for_plane(plane)
        if sem is None:
            await self.app(scope, receive, send)
            return

        acquired = False
        try:
            await asyncio.wait_for(sem.acquire(), timeout=settings.admission_acquire_timeout_sec)
            acquired = True
        except TimeoutError:
            http_admission_rejected_total.labels(plane=plane, reason="capacity").inc()
            response = api_error_response(
                request=request,
                status_code=503,
                detail=f"server at capacity ({plane} plane) — retry shortly",
                code="server_overloaded",
                retryable=True,
                headers={"Retry-After": "5", "X-Spark-Admission-Plane": plane},
            )
            await response(scope, receive, send)
            return

        gauge = http_inflight_gauge.labels(plane=plane)
        gauge.inc()
        try:
            await self.app(scope, receive, send)
        finally:
            gauge.dec()
            if acquired:
                sem.release()
