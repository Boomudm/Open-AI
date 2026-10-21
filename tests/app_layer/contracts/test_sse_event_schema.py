"""Phase 12 — golden SSE chat sequence contract."""

from __future__ import annotations

import json
from typing import Any

GOLDEN_SSE = """\
event: connected
data: {}

event: meta
data: {"route":"rag","intent":"procedure","confidence_tier":"medium","citations_verified":true,"cache_hit":false}

event: token
data: {"delta":"สวัสดี"}

event: token
data: {"delta":"ครับ"}

event: sources
data: {"sources":[],"citations_verified":true}

event: done
data: {"assistant_message_id":"asst-golden-1","cache_hit":false,"intent":"procedure","route":"rag","top_doc_score":0.82,"confidence_tier":"medium","citations_verified":true,"answer_path":"grounded_llm"}
"""


def _parse_sse_blocks(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not event_name:
            continue
        payload: dict[str, Any] = {}
        if data_lines:
            payload = json.loads("\n".join(data_lines))
        events.append((event_name, payload))
    return events


def test_golden_sse_event_order() -> None:
    events = _parse_sse_blocks(GOLDEN_SSE)
    names = [name for name, _ in events]
    assert names[:2] == ["connected", "meta"]
    assert "token" in names
    assert names.index("sources") < names.index("done")
    assert names[-1] == "done"


def test_golden_sse_done_includes_trust_fields() -> None:
    events = _parse_sse_blocks(GOLDEN_SSE)
    done = next(payload for name, payload in events if name == "done")
    for field in (
        "assistant_message_id",
        "cache_hit",
        "confidence_tier",
        "citations_verified",
        "route",
        "answer_path",
    ):
        assert field in done, f"SSE done missing {field}"


def test_sse_schema_allows_provisional_and_citation_block() -> None:
    body = """\
event: token_provisional
data: {"delta":"draft"}

event: citation_block
data: {"text":"verified answer","citations_verified":true}

event: done
data: {"assistant_message_id":"x","cache_hit":false,"intent":"f","route":"rag","top_doc_score":0.1,"confidence_tier":"low","citations_verified":true,"answer_path":"grounded_llm"}
"""
    events = _parse_sse_blocks(body)
    names = [name for name, _ in events]
    assert "token_provisional" in names
    assert "citation_block" in names
    assert names[-1] == "done"
