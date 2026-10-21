"""Dual admission planes — transactional HTTP vs long-lived SSE (app-layer v2 Phase 1)."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Literal

from starlette.requests import Request

from spark.api.platform.route_policy import resolve_route_policy

AdmissionPlane = Literal["transactional", "sse", "exempt"]

_ASK_PATH = re.compile(r"^/api/v1/chat/[0-9a-f-]{36}/ask$", re.I)


def _query_flag(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def _headers_indicate_sse(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    if "text/event-stream" in accept:
        return True
    if request.headers.get("x-spark-stream", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return _query_flag(request.query_params.get("stream"))


def _body_indicates_stream(body: bytes) -> bool:
    if not body:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        compact = body.replace(b" ", b"").lower()
        return b'"stream":true' in compact
    if isinstance(payload, dict):
        return bool(payload.get("stream"))
    return False


def resolve_admission_plane(method: str, path: str, *, request: Request | None = None) -> AdmissionPlane:
    """Static plane from route policy + request hints (no body)."""
    policy = resolve_route_policy(method, path)
    if policy.admission_plane == "exempt":
        return "exempt"

    if request is not None:
        state_plane = getattr(request.state, "admission_plane", None)
        if state_plane in ("sse", "transactional", "exempt"):
            return state_plane

    if policy.admission_plane == "sse":
        return "sse"

    if request is not None and method.upper() == "POST" and _ASK_PATH.match(path):
        if _headers_indicate_sse(request):
            return "sse"

    return "transactional"


async def peek_request_body(
    receive: Callable[[], Awaitable[dict]],
    *,
    max_bytes: int = 65_536,
) -> tuple[bytes, Callable[[], Awaitable[dict]]]:
    """Buffer one HTTP request body and return a replay ``receive`` callable."""
    body = b""
    disconnected = False

    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            disconnected = True
            break
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        body += chunk
        if len(body) > max_bytes:
            body = body[:max_bytes]
        if not message.get("more_body", False):
            break

    sent = False

    async def replay_receive() -> dict:
        nonlocal sent
        if disconnected and sent:
            return {"type": "http.disconnect"}
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return body, replay_receive


async def resolve_admission_plane_for_scope(
    method: str,
    path: str,
    request: Request,
    receive: Callable[[], Awaitable[dict]],
) -> tuple[AdmissionPlane, Callable[[], Awaitable[dict]]]:
    """Resolve plane for middleware; may buffer POST /ask JSON body for ``stream`` flag."""
    plane = resolve_admission_plane(method, path, request=request)
    if plane != "transactional":
        return plane, receive

    if method.upper() != "POST" or not _ASK_PATH.match(path):
        return plane, receive

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return plane, receive

    body, replay = await peek_request_body(receive)
    if _body_indicates_stream(body):
        return "sse", replay
    return "transactional", replay
