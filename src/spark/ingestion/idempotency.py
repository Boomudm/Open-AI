"""Ingest job idempotency keys — duplicate enqueue returns the in-flight job."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.ingestion import IngestionJob

_ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "retrying"})
_TERMINAL_CLEAR_STATUSES = frozenset({"completed", "failed", "dlq", "pending_release", "partial"})


def ingest_idempotency_key(doc_id: uuid.UUID, file_hash: str, config_hash: str) -> str:
    """Stable key for (doc_id, content hash, resolved ingest config)."""
    return f"{doc_id}:{file_hash}:{config_hash}"


async def find_existing_job(session: AsyncSession, key: str) -> IngestionJob | None:
    """Return an in-flight job with the same idempotency key, if any."""
    stmt = (
        select(IngestionJob)
        .where(
            IngestionJob.idempotency_key == key,
            IngestionJob.status.in_(_ACTIVE_JOB_STATUSES),
        )
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def clear_idempotency_key(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Release idempotency slot when a job reaches a terminal state."""
    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == job_id)
        .values(idempotency_key=None)
    )


def is_terminal_job_status(status: str) -> bool:
    return status in _TERMINAL_CLEAR_STATUSES
