"""Phase 14 — WORM append-only audit events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from spark.audit.worm_sink import (
    EVENT_QUARANTINE_RELEASE,
    compute_event_hash,
    verify_event_chain,
)
from spark.db.models.worm_audit import AuditEventImmutable


def test_worm_event_hash_chain_links_previous() -> None:
    ts = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    first = compute_event_hash(
        prev_hash=None,
        event_type=EVENT_QUARANTINE_RELEASE,
        occurred_at=ts,
        actor_id="user-1",
        factory_id="F-01",
        payload={"doc_id": "abc"},
    )
    second = compute_event_hash(
        prev_hash=first,
        event_type="eval_token_issued",
        occurred_at=ts,
        actor_id="user-1",
        factory_id="F-01",
        payload={"config_hash": "deadbeef"},
    )
    assert first != second


def test_verify_event_chain_rejects_prev_hash_tamper() -> None:
    ts = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
    row = AuditEventImmutable(
        event_id=uuid.uuid4(),
        event_type=EVENT_QUARANTINE_RELEASE,
        occurred_at=ts,
        actor_id="user-1",
        factory_id="F-01",
        payload={"doc_id": "abc"},
        prev_hash="deadbeef",
        event_hash="cafebabe" * 8,
    )
    ok, broken = verify_event_chain([row])
    assert ok is False
    assert broken == str(row.event_id)


def test_quarantine_release_uses_worm_event_constant() -> None:
    import inspect

    from spark.api.v1.endpoints import document_release

    source = inspect.getsource(document_release.release_quarantined_document)
    assert "EVENT_QUARANTINE_RELEASE" in source
