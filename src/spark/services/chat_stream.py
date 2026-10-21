"""Server-Sent Events framing for chat ask streaming."""

from __future__ import annotations

import json
from typing import Any


def sse_event(event: str | None, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"


def sse_connected() -> str:
    return sse_event("connected", {})


def sse_token(delta: str) -> str:
    return sse_event("token", {"delta": delta})


def sse_token_provisional(delta: str) -> str:
    return sse_event("token_provisional", {"delta": delta})


def sse_citation_block(text: str, *, citations_verified: bool = True) -> str:
    return sse_event(
        "citation_block",
        {"text": text, "citations_verified": citations_verified},
    )


def sse_meta(payload: dict[str, Any]) -> str:
    return sse_event("meta", payload)


def sse_sources(payload: dict[str, Any]) -> str:
    return sse_event("sources", payload)


def sse_done(payload: dict[str, Any]) -> str:
    return sse_event("done", payload)


def sse_error(code: str, message: str) -> str:
    return sse_event("error", {"code": code, "message": message})


def sse_keepalive() -> str:
    return ": keepalive\n\n"
