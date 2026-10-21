"""Ingest job DLQ, retry bookkeeping, and operator notifications.

Retry authority: Celery autoretry handles transient pipeline failures.
DB ``next_retry_at`` is reserved for operator-scheduled replay only (not set by the pipeline).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionError, IngestionJob

log = get_logger(__name__)


def content_policy_block_job_status() -> str:
    """Content policy findings are logged only; legacy block paths fail, never DLQ."""
    return "failed"


async def increment_job_attempt(job_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        job = await session.get(IngestionJob, job_id)
        if job is None:
            return 0
        attempt = int(job.attempt_count or 0) + 1
        await session.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(attempt_count=attempt)
        )
        await session.commit()
        return attempt


async def mark_job_dlq(
    job_id: uuid.UUID,
    *,
    reason_code: str,
    reason_detail: str,
    doc_id: uuid.UUID | None = None,
) -> None:
    now = datetime.now(tz=timezone.utc)
    error_message = f"{reason_code}: {reason_detail}"[:1000]
    async with AsyncSessionLocal() as session:
        session.add(
            IngestionError(
                job_id=job_id,
                reason_code=str(reason_code)[:50],
                reason_detail=str(reason_detail)[:2000],
            )
        )
        await session.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(
                status="failed",
                dlq_at=None,
                finished_at=now,
                last_error_code=str(reason_code)[:50],
                error_message=error_message,
                next_retry_at=None,
            )
        )
        if doc_id is not None:
            await session.execute(
                update(Document).where(Document.doc_id == doc_id).values(ingest_status="failed")
            )
        await session.commit()
    log.error("ingest_job_failed_after_retries", job_id=str(job_id), reason_code=str(reason_code)[:50])


async def notify_job_dlq(
    *,
    factory_id: str | None,
    job_id: uuid.UUID,
    doc_id: uuid.UUID | None,
    reason_code: str,
    reason_detail: str,
    source_file: str | None = None,
) -> None:
    if not factory_id:
        return
    from spark.services.notification_dispatch_service import notification_dispatch_service

    body = f"{reason_code}: {reason_detail}"[:2000]
    try:
        async with AsyncSessionLocal() as session:
            await notification_dispatch_service.notify_factory(
                session,
                factory_id=str(factory_id),
                event_type="ingest_failed",
                subject=f"Ingest failed: {source_file or doc_id or job_id}",
                body=body,
                context={
                    "job_id": str(job_id),
                    "doc_id": str(doc_id) if doc_id else None,
                    "reason_code": reason_code,
                },
            )
            await session.commit()
    except Exception as exc:
        log.warning("ingest_failed_notify_failed", error=str(exc)[:200])


def mark_job_dlq_sync(
    job_id: str,
    *,
    reason_code: str,
    reason_detail: str,
    doc_id: str | None = None,
) -> None:
    import asyncio

    asyncio.run(
        mark_job_dlq(
            uuid.UUID(job_id),
            reason_code=reason_code,
            reason_detail=reason_detail,
            doc_id=uuid.UUID(doc_id) if doc_id else None,
        )
    )


def notify_job_dlq_sync(
    *,
    factory_id: str | None,
    job_id: str,
    doc_id: str | None,
    reason_code: str,
    reason_detail: str,
    source_file: str | None = None,
) -> None:
    import asyncio

    asyncio.run(
        notify_job_dlq(
            factory_id=factory_id,
            job_id=uuid.UUID(job_id),
            doc_id=uuid.UUID(doc_id) if doc_id else None,
            reason_code=reason_code,
            reason_detail=reason_detail,
            source_file=source_file,
        )
    )


async def skip_breakdown_by_reason(job_id: uuid.UUID) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(IngestionError.reason_code, func.count())
                .where(IngestionError.job_id == job_id)
                .group_by(IngestionError.reason_code)
            )
        ).all()
    breakdown: dict[str, int] = {}
    for code, count in rows:
        key = str(code or "unknown")
        breakdown[key] = int(count or 0)
    return breakdown
