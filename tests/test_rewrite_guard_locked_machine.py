"""Rewrite guard preserves locked machine scope (Phase 10)."""

from __future__ import annotations

from spark.retrieval.preprocess.rewrite_guard import validate_rewrite
from spark.services.session_slots import SessionSlots


def test_rewrite_guard_rejects_dropped_locked_machine() -> None:
    slots = SessionSlots(
        machine_id="MC-001",
        locked_fields=["machine_id"],
    )
    verdict = validate_rewrite(
        "MC-001 overheating follow up",
        "generic overheating troubleshooting",
        slots,
    )
    assert verdict.ok is False
    assert verdict.reason == "locked_machine_dropped"


def test_rewrite_guard_accepts_locked_machine_preservation() -> None:
    slots = SessionSlots(
        machine_id="MC-001",
        locked_fields=["machine_id"],
    )
    verdict = validate_rewrite(
        "MC-001 overheating follow up",
        "MC-001 servo overheating troubleshooting steps",
        slots,
    )
    assert verdict.ok is True
