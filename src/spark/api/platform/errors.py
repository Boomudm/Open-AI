"""Unified API error envelope (app-layer remediation Phase 0)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

TRACE_ID_HEADER = "X-Request-ID"
REQUEST_ID_STATE_KEY = "request_id"


def get_trace_id(request: Request | None) -> str:
    """Return correlation id for this request (Phase 1 middleware will set state)."""
    if request is not None:
        existing = getattr(request.state, REQUEST_ID_STATE_KEY, None)
        if isinstance(existing, str) and existing.strip():
            return existing.strip()
        header = request.headers.get(TRACE_ID_HEADER)
        if header and header.strip():
            trace_id = header.strip()
            request.state.request_id = trace_id
            return trace_id
        trace_id = uuid.uuid4().hex
        request.state.request_id = trace_id
        return trace_id
    return uuid.uuid4().hex


def _retryable_for_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


def _code_for_status(status_code: int, detail: Any) -> str:
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        503: "service_unavailable",
    }
    return mapping.get(status_code, "http_error")


def _normalize_detail(detail: Any) -> str:
    if detail is None:
        return "request failed"
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        inner = detail.get("detail")
        if isinstance(inner, str):
            return inner
        if inner is not None:
            return str(inner)
        return str(detail)
    if isinstance(detail, list):
        return "validation failed"
    return str(detail)


def build_error_envelope(
    *,
    request: Request | None,
    status_code: int,
    detail: Any,
    code: str | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    resolved_code = code or _code_for_status(status_code, detail)
    resolved_retryable = (
        _retryable_for_status(status_code) if retryable is None else retryable
    )
    return {
        "detail": _normalize_detail(detail),
        "code": resolved_code,
        "retryable": resolved_retryable,
        "trace_id": get_trace_id(request),
    }


def api_error_response(
    *,
    request: Request | None,
    status_code: int,
    detail: Any,
    code: str | None = None,
    retryable: bool | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = build_error_envelope(
        request=request,
        status_code=status_code,
        detail=detail,
        code=code,
        retryable=retryable,
    )
    response_headers = dict(headers or {})
    response_headers.setdefault(TRACE_ID_HEADER, body["trace_id"])
    return JSONResponse(status_code=status_code, content=body, headers=response_headers)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    code = None
    retryable = None
    if isinstance(detail, dict):
        code = detail.get("code")
        retryable = detail.get("retryable")
    return api_error_response(
        request=request,
        status_code=exc.status_code,
        detail=detail,
        code=str(code) if code else None,
        retryable=retryable if isinstance(retryable, bool) else None,
        headers=dict(exc.headers or {}),
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return api_error_response(
        request=request,
        status_code=exc.status_code,
        detail=exc.detail,
        headers=dict(exc.headers or {}),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    body = build_error_envelope(
        request=request,
        status_code=422,
        detail="validation failed",
        code="validation_error",
        retryable=False,
    )
    body["errors"] = exc.errors()
    response_headers = {TRACE_ID_HEADER: body["trace_id"]}
    return JSONResponse(status_code=422, content=body, headers=response_headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from spark.core.logging import get_logger

    log = get_logger(__name__)
    trace_id = get_trace_id(request)
    log.exception("unhandled_api_error", trace_id=trace_id, error=str(exc)[:200])
    return api_error_response(
        request=request,
        status_code=500,
        detail="internal server error",
        code="internal_error",
        retryable=True,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register unified error handlers on the FastAPI app."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
