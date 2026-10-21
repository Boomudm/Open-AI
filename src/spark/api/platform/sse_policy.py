"""SSE channel limits and route mapping (app-layer v2 Phase 3)."""

from __future__ import annotations

from typing import Literal

from spark.core.config import settings

SseChannel = Literal["chat_ask", "ingest_job"]

_DEFAULT_CHANNEL_LIMITS: dict[str, int] = {
    "chat_ask": 2,
    "ingest_job": 2,
}


def sse_channel_for_route(method: str, path: str) -> SseChannel | None:
    upper = method.upper()
    if upper == "POST" and path.endswith("/ask") and path.startswith("/api/v1/chat/"):
        return "chat_ask"
    if upper == "GET" and "/ingest/jobs/" in path and path.endswith("/stream"):
        return "ingest_job"
    return None


def per_user_sse_limit() -> int:
    return max(1, int(settings.app_profile.sse_max_connections_per_user))


def per_channel_sse_limit(channel: str) -> int:
    return max(1, int(_DEFAULT_CHANNEL_LIMITS.get(channel, 1)))
