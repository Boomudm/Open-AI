"""Compensating purge outbox for superseded Qdrant generations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from qdrant_client.http.exceptions import UnexpectedResponse

from spark.core.logging import get_logger
from spark.core.metrics import ingest_purge_backlog, ingest_purge_exhausted_total
from spark.core.qdrant_strategy import known_collections
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestPurgeOutbox, IngestionJob
from spark.ingestion.index.qdrant_writer import QdrantWriter

log = get_logger(__name__)

PURGE_MAX_ATTEMPTS = 8


async def enqueue_purge(
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    keep_generation: int,
    collection: str | None,
) -> IngestPurgeOutbox:
    row = IngestPurgeOutbox(
        doc_id=doc_id,
        keep_generation=keep_generation,
        collection=collection,
        status="pending",
        next_retry_at=datetime.now(tz=timezone.utc),
    )
    session.add(row)
    await session.flush()
    await refresh_purge_backlog_metric(session)
    log.info(
        "ingest_purge_enqueued",
        doc_id=str(doc_id),
        keep_generation=keep_generation,
        purge_id=str(row.purge_id),
    )
    return row


async def refresh_purge_backlog_metric(session: AsyncSession) -> None:
    pending = int(
        await session.scalar(
            select(func.count())
            .select_from(IngestPurgeOutbox)
            .where(IngestPurgeOutbox.status == "pending")
        )
        or 0
    )
    ingest_purge_backlog.set(pending)


async def process_purge_row(
    session: AsyncSession,
    row: IngestPurgeOutbox,
    *,
    qdrant_router: QdrantWriter | None = None,
) -> bool:
    router = qdrant_router or QdrantWriter()
    try:
        # Sweep every known base collection, not just row.collection: if a
        # document's routing changed between generations (e.g. it started
        # in spark_docs before a per-type override sent later generations to
        # spark_enterprise_docs), the superseded points sit in the *old*
        # collection while this row only remembers the *new* one — purging
        # a single collection silently orphans the rest forever.
        collections = {row.collection} if row.collection else set()
        collections |= known_collections()
        for collection in collections:
            try:
                await router.delete_by_doc_except_generation(
                    row.doc_id,
                    keep_generation=int(row.keep_generation),
                    collection=collection,
                )
            except UnexpectedResponse as exc:
                if exc.status_code != 404:
                    raise
                log.debug("ingest_purge_collection_missing", collection=collection)
        now = datetime.now(tz=timezone.utc)
        await session.execute(
            update(IngestPurgeOutbox)
            .where(IngestPurgeOutbox.purge_id == row.purge_id)
            .values(status="complete", finished_at=now, last_error=None)
        )
        await session.execute(
            update(Document)
            .where(Document.doc_id == row.doc_id)
            .values(ingest_saga_state="complete")
        )
        log.info(
            "ingest_purge_complete",
            doc_id=str(row.doc_id),
            keep_generation=row.keep_generation,
            purge_id=str(row.purge_id),
        )
        return True
    except Exception as exc:
        attempt = int(row.attempt_count or 0) + 1
        backoff_sec = min(86_400, 30 * (2 ** max(attempt - 1, 0)))
        exhausted = attempt >= PURGE_MAX_ATTEMPTS
        status = "exhausted" if exhausted else "pending"
        await session.execute(
            update(IngestPurgeOutbox)
            .where(IngestPurgeOutbox.purge_id == row.purge_id)
            .values(
                status=status,
                attempt_count=attempt,
                last_error=str(exc)[:500],
                next_retry_at=datetime.now(tz=timezone.utc) + timedelta(seconds=backoff_sec),
            )
        )
        if exhausted:
            ingest_purge_exhausted_total.inc()
            now = datetime.now(tz=timezone.utc)
            await session.execute(
                update(Document)
                .where(Document.doc_id == row.doc_id)
                .values(ingest_saga_state="purge_exhausted")
            )
            latest_job = await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.doc_id == row.doc_id,
                    IngestionJob.status.in_(("completed", "partial")),
                )
                .order_by(IngestionJob.finished_at.desc())
                .limit(1)
            )
            if latest_job is not None:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.job_id == latest_job.job_id)
                    .values(
                        status="failed",
                        dlq_at=None,
                        last_error_code="purge_exhausted",
                        error_message=f"purge exhausted after {attempt} attempts: {exc}"[:1000],
                    )
                )
        log.warning(
            "ingest_purge_failed",
            doc_id=str(row.doc_id),
            purge_id=str(row.purge_id),
            attempt=attempt,
            exhausted=exhausted,
            error=str(exc)[:200],
        )
        return False


async def process_pending_purges(
    session: AsyncSession,
    *,
    limit: int = 20,
    qdrant_router: QdrantWriter | None = None,
) -> dict[str, int]:
    now = datetime.now(tz=timezone.utc)
    rows = (
        await session.execute(
            select(IngestPurgeOutbox)
            .where(
                IngestPurgeOutbox.status == "pending",
                IngestPurgeOutbox.next_retry_at <= now,
            )
            .order_by(IngestPurgeOutbox.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    processed = 0
    succeeded = 0
    for row in rows:
        processed += 1
        if await process_purge_row(session, row, qdrant_router=qdrant_router):
            succeeded += 1

    await refresh_purge_backlog_metric(session)
    return {"processed": processed, "succeeded": succeeded}
