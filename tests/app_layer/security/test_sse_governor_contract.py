"""Phase 12 — SSE connection governor contract."""

from __future__ import annotations

from pathlib import Path

from spark.services.streams.connection_governor import connection_governor


def test_governor_rejects_over_cap() -> None:
    from spark.api.platform import sse_policy

    user_id = "contract-test-user"
    channel = "chat_ask"
    channel_cap = sse_policy.per_channel_sse_limit(channel)
    acquired = 0
    for _ in range(channel_cap + 2):
        result = connection_governor.try_acquire(user_id=user_id, channel=channel)
        if not result.ok:
            break
        acquired += 1
    try:
        assert acquired == channel_cap
        overflow = connection_governor.try_acquire(user_id=user_id, channel=channel)
        assert not overflow.ok
    finally:
        for _ in range(acquired):
            connection_governor.release(user_id=user_id, channel=channel)


def test_chat_stream_service_uses_governor() -> None:
    src = Path("src/spark/services/streams/chat_stream_service.py").read_text(encoding="utf-8")
    assert "sse_connection_slot" in src or "ensure_sse_connection" in src
