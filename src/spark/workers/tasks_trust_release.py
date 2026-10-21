"""Celery task — index quarantined document from stored artifact after admin release."""

from __future__ import annotations

import asyncio
import uuid

from spark.core.logging import get_logger
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.pipeline import run_index_from_artifact
from spark.workers.celery_app import celery_app

log = get_logger(__name__)


async def _index_released(doc_id: uuid.UUID, job_id: uuid.UUID | None) -> dict[str, object]:
    summary = await run_index_from_artifact(doc_id, job_id=job_id)
    if job_id is not None:
        await _update_job_row(job_id, summary)
    return {
        "doc_id": str(doc_id),
        "job_id": str(job_id) if job_id else None,
        "status": summary.status,
        "rows_ok": summary.rows_ok,
        "rows_skipped": summary.rows_skipped,
    }


async def _update_job_row(job_id: uuid.UUID, summary) -> None:  # noqa: ANN001 — JobSummary, avoid import cycle
    """Reflect the release/re-index outcome on the *original* job row.

    run_index_from_artifact only ever updated the Document row — the
    ingestion_jobs row this document was quarantined under stayed at
    'pending_release' forever, even after a successful release, since nothing
    downstream of the release endpoint ever touched ingestion_jobs. From the
    /upload and Documents job trackers this looked identical to a job that
    silently stopped progressing.
    """
    from datetime import datetime, timezone

    from sqlalchemy import update

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.ingestion import IngestionJob

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(
                status=summary.status,
                rows_total=summary.rows_total,
                rows_ok=summary.rows_ok,
                rows_skipped=summary.rows_skipped,
                finished_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()


@celery_app.task(name="spark.workers.tasks_trust_release.index_quarantined_document_task")
def index_quarantined_document_task(doc_id: str, job_id: str | None = None) -> dict[str, object]:
    # Celery prefork: each task gets a fresh event loop; dispose async DB pools
    # before closing the loop so the next task does not inherit stale asyncpg
    # connections tied to a closed loop (see run_pipeline_sync in pipeline.py).
    async def _run() -> dict[str, object]:
        try:
            return await _index_released(uuid.UUID(doc_id), uuid.UUID(job_id) if job_id else None)
        finally:
            from spark.core.database import engine, stream_engine

            await engine.dispose()
            await stream_engine.dispose()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_run())
        log.info("quarantine_release_indexed", **result)
        return result
    except PermanentIngestError as exc:
        log.error(
            "quarantine_release_index_failed",
            doc_id=doc_id,
            reason_code=exc.reason_code,
            detail=exc.reason_detail[:200],
        )
        raise
    finally:
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)
