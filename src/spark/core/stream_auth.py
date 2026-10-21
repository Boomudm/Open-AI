"""Stream ticket + session token extraction (app-layer Phase 2 + v2)."""

from __future__ import annotations

from fastapi import Request

from spark.core.config import settings
from spark.services.streams.ticket_store import (
    StreamChannel,
    StreamTicketClaims,
    TicketConsumeStatus,
    consume_stream_ticket_with_status,
)

AUTH_COOKIE_NAME = "spark_token"


def resolve_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        return token or None
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip() or None
    return None


def stream_ticket_channel_for_path(method: str, path: str) -> StreamChannel | None:
    upper = method.upper()
    if path == "/api/v1/alerts/stream" and upper == "GET":
        return "alerts"
    if upper == "POST" and path.endswith("/ask") and path.startswith("/api/v1/chat/"):
        return "chat_ask"
    if upper == "GET" and "/ingest/jobs/" in path and path.endswith("/stream"):
        return "ingest_job"
    return None


def is_sse_ticket_route(method: str, path: str) -> bool:
    return stream_ticket_channel_for_path(method, path) is not None


def require_ticket_for_sse_route() -> bool:
    return bool(settings.app_profile.require_ticket_for_sse and settings.effective_auth_required)


def _expected_resource_id(channel: StreamChannel, path: str) -> str | None:
    if channel == "alerts":
        return None
    parts = [p for p in path.split("/") if p]
    if channel == "chat_ask":
        if len(parts) >= 4 and parts[-1] == "ask":
            return parts[-2]
    if channel == "ingest_job":
        if len(parts) >= 5 and parts[-1] == "stream":
            return parts[-2]
    return None


async def resolve_stream_ticket(
    request: Request,
) -> tuple[TicketConsumeStatus, StreamTicketClaims | None]:
    channel = stream_ticket_channel_for_path(request.method, request.url.path)
    if channel is None:
        return TicketConsumeStatus.INVALID, None
    ticket = request.query_params.get("ticket")
    if not ticket:
        return TicketConsumeStatus.INVALID, None

    status, claims = await consume_stream_ticket_with_status(ticket)
    if status is not TicketConsumeStatus.OK or claims is None:
        return status, None
    if claims.channel != channel:
        return TicketConsumeStatus.INVALID, None
    expected = _expected_resource_id(channel, request.url.path)
    if expected is not None and claims.resource_id != expected:
        return TicketConsumeStatus.INVALID, None
    return TicketConsumeStatus.OK, claims
