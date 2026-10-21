"""Request correlation ID middleware."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from spark.api.platform.errors import REQUEST_ID_STATE_KEY, TRACE_ID_HEADER
from spark.core.logging import bind_request_context, clear_request_context


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(TRACE_ID_HEADER, "").strip()
        trace_id = incoming or uuid.uuid4().hex
        setattr(request.state, REQUEST_ID_STATE_KEY, trace_id)
        bind_request_context(request_id=trace_id)
        try:
            response = await call_next(request)
            response.headers.setdefault(TRACE_ID_HEADER, trace_id)
            return response
        finally:
            clear_request_context()
