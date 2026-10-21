"""Phase 14 — WORM audit hash chain integrity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from spark.audit.worm_sink import (
    compute_event_hash,
    verify_event_chain,
)
from spark.db.models.worm_audit import AuditEventImmutable


def test_compute_event_hash_chains_to_previous() -> None:
    ts = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    first = compute_event_hash(
        prev_hash=None,
        event_type="ingest_swap_committed",
        occurred_at=ts,
        actor_id=None,
        factory_id="F-01",
        payload={"doc_id": "abc"},
    )
    second = compute_event_hash(
        prev_hash=first,
        event_type="scope_broadening",
        occurred_at=ts,
        actor_id="user-1",
        factory_id="F-01",
        payload={"fallback_level": 1},
    )
    assert first != second
    assert len(first) == 64
    assert len(second) == 64


def test_verify_event_chain_detects_tamper() -> None:
    ts = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    payload = {"doc_id": "x"}
    h1 = compute_event_hash(
        prev_hash=None,
        event_type="ingest_swap_committed",
        occurred_at=ts,
        actor_id=None,
        factory_id="F-01",
        payload=payload,
    )
    row1 = AuditEventImmutable(
        event_id=uuid.uuid4(),
        event_type="ingest_swap_committed",
        occurred_at=ts,
        actor_id=None,
        factory_id="F-01",
        payload=payload,
        prev_hash=None,
        event_hash=h1,
    )
    row2 = AuditEventImmutable(
        event_id=uuid.uuid4(),
        event_type="scope_broadening",
        occurred_at=ts,
        actor_id=None,
        factory_id="F-01",
        payload={"level": 1},
        prev_hash=h1,
        event_hash="deadbeef" * 8,
    )
    ok, broken = verify_event_chain([row1, row2])
    assert ok is False
    assert broken == str(row2.event_id)


def test_verify_event_chain_accepts_valid_sequence() -> None:
    ts = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    h1 = compute_event_hash(
        prev_hash=None,
        event_type="a",
        occurred_at=ts,
        actor_id=None,
        factory_id=None,
        payload={},
    )
    h2 = compute_event_hash(
        prev_hash=h1,
        event_type="b",
        occurred_at=ts,
        actor_id=None,
        factory_id=None,
        payload={},
    )
    rows = [
        AuditEventImmutable(
            event_id=uuid.uuid4(),
            event_type="a",
            occurred_at=ts,
            actor_id=None,
            factory_id=None,
            payload={},
            prev_hash=None,
            event_hash=h1,
        ),
        AuditEventImmutable(
            event_id=uuid.uuid4(),
            event_type="b",
            occurred_at=ts,
            actor_id=None,
            factory_id=None,
            payload={},
            prev_hash=h1,
            event_hash=h2,
        ),
    ]
    ok, broken = verify_event_chain(rows)
    assert ok is True
    assert broken is None
