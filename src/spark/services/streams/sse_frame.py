"""Shared SSE frame serialization (app-layer v2 Phase 3)."""

from __future__ import annotations

import json
from typing import Any


def sse_event(
    event: str,
    data: dict[str, Any] | str,
    *,
    event_id: str | None = None,
) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def sse_data(data: dict[str, Any], *, event: str | None = None) -> str:
    if event:
        return sse_event(event, data)
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


def sse_comment(text: str) -> str:
    return f": {text}\n\n"


def sse_retry(ms: int) -> str:
    return f"retry: {max(0, int(ms))}\n\n"


def sse_token_provisional(delta: str) -> str:
    return sse_event("token_provisional", {"delta": delta})


def sse_citation_block(text: str, *, citations_verified: bool = True) -> str:
    return sse_event(
        "citation_block",
        {"text": text, "citations_verified": citations_verified},
    )
