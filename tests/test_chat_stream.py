"""Tests for chat SSE framing helpers."""

from __future__ import annotations

from spark.services.chat_stream import sse_done, sse_meta, sse_token


def test_sse_token_frame() -> None:
    frame = sse_token("สวัสดี")
    assert "event: token" in frame
    assert '"delta": "สวัสดี"' in frame


def test_sse_meta_frame() -> None:
    frame = sse_meta({"intent": "factual", "route": "rag"})
    assert "event: meta" in frame
    assert '"route": "rag"' in frame


def test_sse_done_frame() -> None:
    frame = sse_done({"assistant_message_id": "abc"})
    assert "event: done" in frame
