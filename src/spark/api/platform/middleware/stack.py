"""Register platform HTTP middleware (app-layer Phase 1 + v2).

Starlette/FastAPI: **last** ``add_middleware`` call = **outermost** (runs first on request).

Outermost → innermost:
  SecurityHeaders → RequestId → Timeout → GlobalRateLimit → Concurrency (dual-plane ASGI)
  → CORS → Metrics → auth
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from spark.api.platform.middleware.concurrency import ConcurrencyLimitMiddleware
from spark.api.platform.middleware.rate_limit import GlobalRateLimitMiddleware
from spark.api.platform.middleware.request_id import RequestIdMiddleware
from spark.api.platform.middleware.security_headers import SecurityHeadersMiddleware
from spark.api.platform.middleware.timeout import TimeoutMiddleware
from spark.core.config import settings
from spark.core.metrics import MetricsMiddleware


class RequestBodyLimitMiddleware:
    """Reject requests with Content-Length exceeding the configured limit."""

    def __init__(self, app, max_bytes: int = 52_428_800) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            cl = headers.get(b"content-length")
            if cl is not None:
                try:
                    if int(cl) > self.max_bytes:
                        from starlette.responses import JSONResponse
                        response = JSONResponse(
                            {"detail": "request body too large", "code": "payload_too_large"},
                            status_code=413,
                        )
                        await response(scope, receive, send)
                        return
                except (ValueError, TypeError):
                    pass
        await self.app(scope, receive, send)


def register_platform_middleware(app: FastAPI) -> None:
    """Attach auth + platform middleware in documented order.

    Outermost → innermost:
      SecurityHeaders → RequestId → Timeout → GlobalRateLimit → BodyLimit
      → Concurrency → CORS → GZip → Metrics → auth
    """
    from spark.core.security import auth_middleware

    app.middleware("http")(auth_middleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_origin_list != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ConcurrencyLimitMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(GlobalRateLimitMiddleware)
    app.add_middleware(TimeoutMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
