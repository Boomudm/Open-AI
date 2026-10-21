"""Per-route HTTP policies — timeouts, admission planes, rate-limit classes (v2 Phase 1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from spark.api.platform.sse_policy import sse_channel_for_route

AdmissionPlaneKind = Literal["transactional", "sse", "exempt"]

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


@dataclass(frozen=True)
class RoutePolicy:
    timeout_sec: int | None = 120
    rate_limit_exempt: bool = False
    concurrency_exempt: bool = False
    rate_limit_class: str = "default"
    admission_plane: AdmissionPlaneKind = "transactional"


_HEALTH_PATHS = frozenset({"/", "/healthz", "/readyz", "/metrics"})

_EXEMPT = RoutePolicy(
    timeout_sec=30,
    rate_limit_exempt=True,
    concurrency_exempt=True,
    admission_plane="exempt",
)

_SSE_STREAM = RoutePolicy(
    timeout_sec=None,
    rate_limit_class="stream",
    admission_plane="sse",
)

# Explicit overrides keyed by (METHOD, normalized_path)
ROUTE_POLICIES: dict[tuple[str, str], RoutePolicy] = {
    ("POST", "/api/v1/chat/{id}/ask"): RoutePolicy(
        timeout_sec=180,
        rate_limit_class="rag",
        admission_plane="transactional",
    ),
    ("GET", "/api/v1/ingest/jobs/{id}/stream"): _SSE_STREAM,
    ("POST", "/api/v1/auth/login"): RoutePolicy(
        timeout_sec=30,
        rate_limit_class="auth",
    ),
    ("POST", "/api/v1/auth/oauth/exchange"): RoutePolicy(
        timeout_sec=30,
        rate_limit_class="auth",
    ),
}


def _normalize_path(path: str) -> str:
    segments: list[str] = []
    for seg in path.split("/"):
        if _UUID.fullmatch(seg):
            segments.append("{id}")
        elif seg.isdigit():
            segments.append("{num}")
        else:
            segments.append(seg)
    return "/".join(segments)


def resolve_route_policy(method: str, path: str) -> RoutePolicy:
    if path in _HEALTH_PATHS:
        return _EXEMPT
    normalized = _normalize_path(path)
    key = (method.upper(), normalized)
    if key in ROUTE_POLICIES:
        return ROUTE_POLICIES[key]
    if normalized.endswith("/stream"):
        return _SSE_STREAM
    if method.upper() == "POST" and normalized.endswith("/ask"):
        return RoutePolicy(timeout_sec=180, rate_limit_class="rag", admission_plane="transactional")
    return RoutePolicy()


def resolve_sse_channel(method: str, path: str) -> str | None:
    """Map HTTP route to SSE governor channel (v2 Phase 3)."""
    return sse_channel_for_route(method, path)
