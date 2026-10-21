"""Session slot state v3 — validated multi-turn RAG scope with evidence TTL (Phase 12)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from spark.core.logging import get_logger
from spark.retrieval.models import RAGFilter, default_latest_revision_only

log = get_logger(__name__)

# component_id intentionally absent — machines exist only to bind documents;
# there is no component scope (product decision 2026-07). The model field is
# kept so old session contexts still validate, but it is never propagated.
_LOCKABLE_FIELDS = frozenset(
    {"factory_id", "machine_id", "document_type", "revision"}
)
_REVISION_RE = re.compile(r"(?i)\brev(?:ision)?\.?\s*([A-Z]|\d+)\b")
_OTHER_MACHINE_MARKERS = (
    "เครื่องอื่น",
    "other machine",
    "another machine",
    "คนละเครื่อง",
)


class SessionSlots(BaseModel):
    factory_id: str | None = None
    machine_id: str | None = None
    component_id: str | None = None
    document_type: str | None = None
    revision: str | None = None
    # Not persisted across turns by apply_turn: a drawing scope silently
    # sticking to later unrelated questions would narrow retrieval invisibly.
    # merge_filter still reads it so an explicit request filter (or restored
    # session context) can scope a single ask to one drawing number.
    drawing_no: str | None = None
    confirmed_machine_id: str | None = None
    # Answer-method scope the thread settled on ("machinery" | "enterprise").
    # Lets a context-light follow-up inherit the established scope instead of
    # being re-routed from a keyword-less bare question. Only content scopes
    # are stored — chitchat/clarify turns leave it untouched (carried forward).
    pipeline: str | None = None
    locked_fields: list[str] = Field(default_factory=list)
    last_retrieved_chunk_ids: list[str] = Field(default_factory=list)
    last_user_question: str | None = None
    latest_revision_only: bool | None = None
    turn_count: int = 0
    evidence_turn_ttl: int = 3
    last_evidence_turn: int = 0

    @field_validator("locked_fields", mode="before")
    @classmethod
    def _normalize_locked_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (set, frozenset)):
            return sorted(str(item) for item in value if item)
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return []

    def is_locked(self, field: str) -> bool:
        return field in self.locked_fields

    def effective_machine_id(self) -> str | None:
        return self.confirmed_machine_id or self.machine_id

    @property
    def locked_machine_id(self) -> str | None:
        if self.is_locked("machine_id"):
            return self.effective_machine_id()
        return None

    @property
    def locked_revision(self) -> str | None:
        if self.is_locked("revision"):
            return self.revision
        return None

    def follow_up_chunk_ids(self) -> list[str]:
        """Return prior chunk memory only while evidence TTL has not expired."""
        if not self.last_retrieved_chunk_ids:
            return []
        if self.last_evidence_turn <= 0:
            return list(self.last_retrieved_chunk_ids)
        age = self.turn_count - self.last_evidence_turn
        if age > self.evidence_turn_ttl:
            return []
        return list(self.last_retrieved_chunk_ids)

    def evidence_age_turns(self) -> int | None:
        if self.last_evidence_turn <= 0:
            return None
        return max(0, self.turn_count - self.last_evidence_turn)

    @classmethod
    def evidence_age_from_context(cls, context: dict[str, Any] | None) -> int | None:
        return cls.from_context(context).evidence_age_turns()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None) -> SessionSlots:
        if not context:
            return cls()
        known = cls.model_fields.keys()
        payload = {key: context[key] for key in known if key in context}
        return cls.model_validate(payload)

    def to_context_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if not self.locked_fields:
            data.pop("locked_fields", None)
        if not self.last_retrieved_chunk_ids:
            data.pop("last_retrieved_chunk_ids", None)
        return data

    def merge_filter(self, req_filter: Any | None) -> RAGFilter:
        req_dict = req_filter.model_dump(exclude_none=True) if req_filter else {}
        document_type = req_dict.get("document_type") or self.document_type
        latest_revision_only = req_dict.get("latest_revision_only")
        if latest_revision_only is None:
            if self.latest_revision_only is not None:
                latest_revision_only = self.latest_revision_only
            elif self.revision:
                latest_revision_only = False
            else:
                latest_revision_only = default_latest_revision_only(document_type)

        machine_id = req_dict.get("machine_id")
        if machine_id is None or self.is_locked("machine_id"):
            machine_id = self.effective_machine_id()

        def _pick(field: str) -> Any:
            if self.is_locked(field):
                return getattr(self, field)
            return req_dict.get(field) or getattr(self, field)

        return RAGFilter(
            factory_id=_pick("factory_id"),
            machine_id=machine_id,
            document_category=req_dict.get("document_category"),
            document_type=document_type,
            language=req_dict.get("language"),
            only_active=bool(req_dict.get("only_active", False)),
            latest_revision_only=bool(latest_revision_only),
            revision=_pick("revision"),
            drawing_no=req_dict.get("drawing_no") or _pick("drawing_no"),
        )

    def apply_turn(
        self,
        *,
        question: str,
        rf: RAGFilter,
        chunk_ids: list[str],
        locked_machine_id: str | None = None,
        pipeline: str | None = None,
    ) -> SessionSlots:
        updated = self.model_copy(deep=True)
        locked = set(updated.locked_fields)

        # Persist only a content scope; a transient chitchat/clarify turn keeps
        # the thread's prior scope (carried by the deep copy) rather than
        # clearing it, so the next real follow-up still routes correctly.
        if pipeline in ("machinery", "enterprise"):
            updated.pipeline = pipeline

        for field in ("factory_id", "machine_id", "document_type", "revision"):
            value = getattr(rf, field, None)
            if value is None:
                continue
            if field in locked and getattr(updated, field) not in (None, value):
                continue
            setattr(updated, field, value)

        revision_from_question = extract_revision_from_question(question)
        if revision_from_question and not updated.is_locked("revision"):
            updated.revision = revision_from_question

        if locked_machine_id:
            updated.confirmed_machine_id = locked_machine_id
            updated.machine_id = locked_machine_id
            locked.add("machine_id")

        updated.last_user_question = question.strip() or None
        updated.turn_count = self.turn_count + 1
        if chunk_ids:
            updated.last_retrieved_chunk_ids = chunk_ids[:32]
            updated.last_evidence_turn = updated.turn_count
        updated.latest_revision_only = rf.latest_revision_only
        updated.locked_fields = sorted(locked)
        return updated

    def as_rewrite_context(self) -> dict[str, Any]:
        ctx = self.to_context_dict()
        machine = self.effective_machine_id()
        if machine:
            ctx["machine_id"] = machine
            ctx["confirmed_machine_id"] = self.confirmed_machine_id or machine
        return ctx


def session_slots_hash(slots: SessionSlots | dict[str, Any] | None) -> str:
    payload = (
        slots.to_context_dict()
        if isinstance(slots, SessionSlots)
        else dict(slots or {})
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def extract_revision_from_question(question: str) -> str | None:
    match = _REVISION_RE.search(question or "")
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return f"Rev {token}"
    return f"Rev {token.upper()}"


def requests_other_machine_scope(question: str, locked_machine_id: str | None) -> bool:
    if not locked_machine_id:
        return False
    lower = (question or "").lower()
    if any(marker in lower for marker in _OTHER_MACHINE_MARKERS):
        return True
    from spark.retrieval.preprocess.follow_up import machine_ids_in_text

    for machine_id in machine_ids_in_text(question):
        if machine_id.upper() != locked_machine_id.upper():
            return True
    return False


def merge_session_slots(
    session_context: dict[str, Any] | None,
    req_filter: Any | None,
    *,
    locked_machine_id: str | None = None,
) -> tuple[SessionSlots, RAGFilter]:
    slots = SessionSlots.from_context(session_context)
    if locked_machine_id:
        slots = slots.model_copy(
            update={
                "confirmed_machine_id": locked_machine_id,
                "machine_id": locked_machine_id,
                "locked_fields": sorted(set(slots.locked_fields) | {"machine_id"}),
            }
        )
    rf = slots.merge_filter(req_filter)
    return slots, rf


def persist_session_slots(session_context: dict[str, Any] | None, slots: SessionSlots) -> dict[str, Any]:
    merged = dict(session_context or {})
    merged.update(slots.to_context_dict())
    return merged


def log_slot_diff(before: SessionSlots, after: SessionSlots) -> None:
    before_dict = before.model_dump()
    after_dict = after.model_dump()
    diff = {
        key: {"from": before_dict.get(key), "to": after_dict.get(key)}
        for key in SessionSlots.model_fields
        if before_dict.get(key) != after_dict.get(key)
    }
    if diff:
        log.info("session_slots_updated", diff=diff)
