"""Per-request asyncio deadline middleware (pure ASGI, v2 Phase 1)."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from spark.api.platform.errors import api_error_response
from spark.api.platform.route_policy import resolve_route_policy
from spark.core.config import settings


class TimeoutMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        policy = resolve_route_policy(method, path)
        timeout_sec = (
            policy.timeout_sec
            if policy.timeout_sec is not None
            else settings.http_default_timeout_sec
        )
        if timeout_sec is None or timeout_sec <= 0:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        async def _call_app() -> None:
            await self.app(scope, receive, send)

        try:
            await asyncio.wait_for(_call_app(), timeout=timeout_sec)
        except TimeoutError:
            response = api_error_response(
                request=request,
                status_code=504,
                detail="request timed out",
                code="request_timeout",
                retryable=True,
            )
            await response(scope, receive, send)
