"""Phase 12 — stream ticket security contract."""

from __future__ import annotations

from pathlib import Path


def test_ticket_store_uses_atomic_pop() -> None:
    src = Path("src/spark/services/streams/ticket_store.py").read_text(encoding="utf-8")
    assert "atomic_pop_json" in src
    assert "pop_json" not in src.replace("atomic_pop_json", "")


def test_stream_auth_validates_freshness() -> None:
    ticket_src = Path("src/spark/services/streams/ticket_store.py").read_text(encoding="utf-8")
    assert "token_version" in ticket_src
    assert "consume_stream_ticket_with_status" in ticket_src


def test_streams_endpoint_returns_remaining_connections() -> None:
    src = Path("src/spark/api/v1/endpoints/streams.py").read_text(encoding="utf-8")
    assert "remaining_connections" in src
