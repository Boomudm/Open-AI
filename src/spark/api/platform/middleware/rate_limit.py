"""Global HTTP rate limiting — atomic IP sliding window (app-layer v2 Phase 1, pure ASGI)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from spark.api.platform.errors import api_error_response
from spark.api.platform.route_policy import resolve_route_policy
from spark.api.platform.rate_limit_lua import increment_sliding_window
from spark.api.platform.trusted_proxy import client_ip  # re-export for callers
from spark.core.config import settings
from spark.core.metrics import http_rate_limited_total


def global_rate_limit_rpm() -> int:
    return settings.effective_global_rate_limit_rpm


def global_rate_limit_burst() -> int:
    return max(0, int(settings.global_rate_limit_burst or 0))


def effective_rate_limit_for_class(rate_class: str) -> int:
    """Per-class RPM caps; falls back to global effective RPM + burst."""
    base = global_rate_limit_rpm()
    burst = global_rate_limit_burst()
    overrides = {
        "rag": base,
        "stream": base,
        "auth": min(base, 120) if base > 0 else 0,
        "default": base,
    }
    rpm = int(overrides.get(rate_class, base))
    if rpm <= 0:
        return 0
    return rpm + burst


class GlobalRateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        policy = resolve_route_policy(method, path)
        if policy.rate_limit_exempt:
            await self.app(scope, receive, send)
            return

        limit = effective_rate_limit_for_class(policy.rate_limit_class)
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        window_sec = 60
        ip = client_ip(request)
        key = f"spark:http:rate:ip:{ip}:{policy.rate_limit_class}"
        used = await increment_sliding_window(key, window_sec=window_sec)
        if used > limit:
            http_rate_limited_total.labels(
                scope="global_ip",
                rate_class=policy.rate_limit_class,
            ).inc()
            response = api_error_response(
                request=request,
                status_code=429,
                detail="global API rate limit exceeded",
                code="rate_limit_exceeded",
                retryable=True,
                headers={"Retry-After": str(window_sec)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
