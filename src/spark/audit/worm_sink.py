"""Hash-chained immutable audit sink (Phase 14)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.db.models.worm_audit import AuditEventImmutable

log = get_logger(__name__)

GENESIS_HASH = "0" * 64

# Standard WORM event types (Phase 14).
EVENT_QUARANTINE_RELEASE = "quarantine_release"
EVENT_CIRCUIT_RESET = "circuit_reset"
EVENT_EVAL_TOKEN_ISSUED = "eval_token_issued"
EVENT_INGEST_SWAP_COMMITTED = "ingest_swap_committed"
EVENT_RAG_SCOPE_BROADENED = "rag_scope_broadened"
EVENT_SAFETY_QUERY_REFUSED = "safety_query_refused"

WORM_EVENT_TYPES = frozenset(
    {
        EVENT_QUARANTINE_RELEASE,
        EVENT_CIRCUIT_RESET,
        EVENT_EVAL_TOKEN_ISSUED,
        EVENT_INGEST_SWAP_COMMITTED,
        EVENT_RAG_SCOPE_BROADENED,
        EVENT_SAFETY_QUERY_REFUSED,
        # Legacy aliases retained for historical rows
        "document_released",
        "circuit_reset_manual",
        "scope_broadening",
    }
)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    occurred_at: datetime
    actor_id: str | None
    factory_id: str | None
    payload: dict[str, Any]
    prev_hash: str | None
    event_hash: str


def _canonical_payload(
    *,
    prev_hash: str | None,
    event_type: str,
    occurred_at: datetime,
    actor_id: str | None,
    factory_id: str | None,
    payload: dict[str, Any],
) -> str:
    body = {
        "prev_hash": prev_hash or "",
        "event_type": event_type,
        "occurred_at": occurred_at.astimezone(UTC).isoformat(),
        "actor_id": actor_id or "",
        "factory_id": factory_id or "",
        "payload": payload,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(
    *,
    prev_hash: str | None,
    event_type: str,
    occurred_at: datetime,
    actor_id: str | None,
    factory_id: str | None,
    payload: dict[str, Any],
) -> str:
    canonical = _canonical_payload(
        prev_hash=prev_hash,
        event_type=event_type,
        occurred_at=occurred_at,
        actor_id=actor_id,
        factory_id=factory_id,
        payload=payload,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_event_chain(events: list[AuditEventImmutable]) -> tuple[bool, str | None]:
    """Return (ok, first_broken_event_id). Events must be ordered oldest-first."""
    expected_prev: str | None = None
    for row in events:
        if row.prev_hash != expected_prev:
            return False, str(row.event_id)
        recomputed = compute_event_hash(
            prev_hash=row.prev_hash,
            event_type=row.event_type,
            occurred_at=row.occurred_at,
            actor_id=row.actor_id,
            factory_id=row.factory_id,
            payload=dict(row.payload or {}),
        )
        if recomputed != row.event_hash:
            return False, str(row.event_id)
        expected_prev = row.event_hash
    return True, None


class PostgresWORMAuditSink:
    """Append-only Postgres audit sink with SHA-256 hash chain."""

    async def _latest_hash(self, session: AsyncSession) -> str | None:
        row = (
            await session.execute(
                select(AuditEventImmutable.event_hash)
                .order_by(AuditEventImmutable.occurred_at.desc(), AuditEventImmutable.event_id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return str(row) if row else None

    async def append(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        payload: dict[str, Any],
        actor_id: str | uuid.UUID | None = None,
        factory_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEvent:
        ts = occurred_at or datetime.now(tz=UTC)
        prev_hash = await self._latest_hash(session)
        actor = str(actor_id) if actor_id is not None else None
        event_hash = compute_event_hash(
            prev_hash=prev_hash,
            event_type=event_type,
            occurred_at=ts,
            actor_id=actor,
            factory_id=factory_id,
            payload=payload,
        )
        row = AuditEventImmutable(
            event_type=event_type,
            occurred_at=ts,
            actor_id=actor,
            factory_id=factory_id,
            payload=payload,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )
        session.add(row)
        await session.flush()
        log.info(
            "worm_audit_appended",
            event_type=event_type,
            event_hash=event_hash,
            factory_id=factory_id,
        )
        return AuditEvent(
            event_type=event_type,
            occurred_at=ts,
            actor_id=actor,
            factory_id=factory_id,
            payload=payload,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )


worm_audit_sink = PostgresWORMAuditSink()


async def append_worm_audit(
    event_type: str,
    *,
    payload: dict[str, Any],
    actor_id: str | uuid.UUID | None = None,
    factory_id: str | None = None,
) -> str | None:
    """Append audit event in its own transaction; returns event_hash or None on failure."""
    try:
        from spark.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            event = await worm_audit_sink.append(
                session,
                event_type=event_type,
                payload=payload,
                actor_id=actor_id,
                factory_id=factory_id,
            )
            await session.commit()
            return event.event_hash
    except Exception as exc:
        log.warning(
            "worm_audit_append_failed",
            event_type=event_type,
            error=str(exc)[:200],
        )
        return None


def schedule_worm_audit(
    event_type: str,
    *,
    payload: dict[str, Any],
    actor_id: str | uuid.UUID | None = None,
    factory_id: str | None = None,
) -> None:
    """Fire-and-forget worm audit append from sync or async callers."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            append_worm_audit(
                event_type,
                payload=payload,
                actor_id=actor_id,
                factory_id=factory_id,
            )
        )
    except RuntimeError:
        try:
            asyncio.run(
                append_worm_audit(
                    event_type,
                    payload=payload,
                    actor_id=actor_id,
                    factory_id=factory_id,
                )
            )
        except Exception:
            pass
