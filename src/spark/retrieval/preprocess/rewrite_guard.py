"""Post-LLM rewrite validation — preserve locked session slots (Phase 10)."""

from __future__ import annotations

from dataclasses import dataclass

from spark.services.session_slots import SessionSlots


@dataclass(frozen=True)
class RewriteVerdict:
    ok: bool
    reason: str | None = None


def validate_rewrite(
    original: str,
    rewritten: str,
    locked_slots: SessionSlots,
) -> RewriteVerdict:
    """Reject rewrites that drop locked machine_id or revision scope."""
    original_text = (original or "").strip()
    rewritten_text = (rewritten or "").strip()
    if not rewritten_text:
        return RewriteVerdict(False, "empty_rewrite")

    if locked_slots.is_locked("machine_id") and locked_slots.machine_id:
        machine_id = str(locked_slots.machine_id).strip()
        if machine_id.lower() not in rewritten_text.lower():
            return RewriteVerdict(False, "locked_machine_dropped")

    if locked_slots.is_locked("revision") and locked_slots.revision:
        revision = str(locked_slots.revision).strip()
        if revision.lower() not in rewritten_text.lower() and revision.lower() not in original_text.lower():
            return RewriteVerdict(False, "locked_revision_dropped")

    if locked_slots.is_locked("factory_id") and locked_slots.factory_id:
        factory_id = str(locked_slots.factory_id).strip()
        if factory_id.lower() not in rewritten_text.lower():
            return RewriteVerdict(False, "locked_factory_dropped")

    return RewriteVerdict(True)
