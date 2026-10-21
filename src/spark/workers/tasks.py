from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger
from spark.ingestion.errors import PermanentIngestError, TransientIngestError
from spark.ingestion.reason_codes import ReasonCode
from spark.ingestion.job_reliability import mark_job_dlq_sync, notify_job_dlq_sync
from spark.storage import get_storage
from spark.workers.celery_app import celery_app

log = get_logger(__name__)

_MAX_RETRIES = 5


@celery_app.task(
    name="spark.workers.tasks.ingest_document",
    bind=True,
    autoretry_for=(TransientIngestError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=_MAX_RETRIES,
    acks_late=True,
)
def ingest_document_task(
    self,
    doc_id: str,
    document_type: str,
    document_context: dict[str, Any],
    job_id: str | None = None,
    storage_uri: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    from spark.ingestion.pipeline import run_pipeline_sync

    storage = get_storage()
    log.info(
        "task_ingest_start",
        task_id=self.request.id,
        doc_id=doc_id,
        document_type=document_type,
        storage_uri=storage_uri,
        file=file_path,
        attempt=self.request.retries + 1,
        max_retries=_MAX_RETRIES,
    )

    try:
        if storage_uri:
            with storage.materialize_local(storage_uri) as materialized:
                summary = run_pipeline_sync(
                    doc_id=uuid.UUID(doc_id),
                    file_path=materialized,
                    document_type=document_type,
                    document_context=document_context,
                    job_id=uuid.UUID(job_id) if job_id else None,
                )
        elif file_path:
            summary = run_pipeline_sync(
                doc_id=uuid.UUID(doc_id),
                file_path=Path(file_path),
                document_type=document_type,
                document_context=document_context,
                job_id=uuid.UUID(job_id) if job_id else None,
            )
        else:
            raise PermanentIngestError("pipeline_failed", "ingest_document_task requires storage_uri or file_path")
    except TransientIngestError as exc:
        if self.request.retries >= _MAX_RETRIES and job_id:
            log.error(
                "task_ingest_max_retries",
                job_id=job_id,
                doc_id=doc_id,
                reason_code=exc.reason_code,
            )
            mark_job_dlq_sync(
                job_id,
                reason_code=exc.reason_code,
                reason_detail=exc.reason_detail,
                doc_id=doc_id,
            )
            notify_job_dlq_sync(
                factory_id=document_context.get("factory_id"),
                job_id=job_id,
                doc_id=doc_id,
                reason_code=exc.reason_code,
                reason_detail=exc.reason_detail,
                source_file=document_context.get("source_file"),
            )
        raise
    except PermanentIngestError as exc:
        if exc.reason_code == ReasonCode.DUPLICATE_JOB_IN_PROGRESS.value:
            log.info(
                "task_ingest_skipped_duplicate",
                task_id=self.request.id,
                doc_id=doc_id,
                job_id=job_id,
            )
            return {
                "job_id": job_id,
                "doc_id": doc_id,
                "status": "job_skipped_duplicate",
                "reason_code": exc.reason_code,
                "error": exc.reason_detail,
            }
        raise

    return {
        "job_id": str(summary.job_id),
        "doc_id": str(summary.doc_id),
        "status": summary.status,
        "rows_total": summary.rows_total,
        "rows_ok": summary.rows_ok,
        "rows_skipped": summary.rows_skipped,
        "error": summary.error,
    }


@celery_app.task(name="spark.workers.tasks.cleanup_ingest_temp_task")
def cleanup_ingest_temp_task() -> dict[str, int]:
    from spark.storage.temp import cleanup_stale_ingest_temp

    removed = cleanup_stale_ingest_temp()
    return {"removed": removed}


def _known_celery_task_ids() -> set[str] | None:
    """Task ids visible to Celery: worker active/reserved/scheduled + broker queues.

    Returns None when the picture can't be trusted (no worker responded, broker
    unreadable) — callers must then skip reaping rather than guess.
    """
    import json

    ids: set[str] = set()
    try:
        insp = celery_app.control.inspect(timeout=5)
        worker_buckets = [insp.active(), insp.reserved(), insp.scheduled()]
        if all(bucket is None for bucket in worker_buckets):
            return None
        for bucket in worker_buckets:
            for tasks in (bucket or {}).values():
                for item in tasks or []:
                    task_id = item.get("id") or (item.get("request") or {}).get("id")
                    if task_id:
                        ids.add(str(task_id))
        with celery_app.connection_or_acquire() as conn:
            client = conn.default_channel.client
            for queue in ("celery", "ocr_heavy"):
                for raw in client.lrange(queue, 0, -1) or []:
                    try:
                        payload = json.loads(raw)
                        task_id = (payload.get("headers") or {}).get("id")
                        if task_id:
                            ids.add(str(task_id))
                    except Exception:  # noqa: BLE001 — skip unparseable entries
                        continue
    except Exception as exc:  # noqa: BLE001 — treat any failure as "unknown"
        log.warning("celery_task_id_scan_failed", error=str(exc)[:200])
        return None
    return ids


@celery_app.task(name="spark.workers.tasks.rescue_stuck_pending_task")
def rescue_stuck_pending_task() -> dict[str, int]:
    """Re-queue documents stuck in 'pending' with no active ingest job.

    A document lands in this state when its Celery task was lost (e.g. worker
    crash, Redis connection failure) after the document was marked pending but
    before or during task execution. Runs every 5 minutes via beat schedule.

    Also reaps job rows stranded in queued/running whose Celery task no longer
    exists anywhere (worker crash mid-run, broker restart dropping the queue).
    Without this, the "active job" guard below treated those corpses as live
    and the affected documents never recovered.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document
    from spark.db.models.ingestion import IngestionJob

    STUCK_AFTER_MINUTES = 10

    async def _reap_lost_jobs(cutoff: "datetime") -> int:
        known_ids = _known_celery_task_ids()
        if known_ids is None:
            return 0
        reaped = 0
        async with AsyncSessionLocal() as session:
            stuck_jobs = (
                await session.execute(
                    select(IngestionJob).where(
                        IngestionJob.status.in_(("queued", "running", "started")),
                        IngestionJob.created_at < cutoff,
                    )
                )
            ).scalars().all()
            for job in stuck_jobs:
                if job.celery_task_id and job.celery_task_id in known_ids:
                    continue
                job.status = "lost"
                job.error_message = (
                    "celery task missing from workers and broker (crash/restart); "
                    "document requeued by rescue task"
                )
                reaped += 1
                log.warning(
                    "rescue_reaped_lost_job",
                    job_id=str(job.job_id),
                    doc_id=str(job.doc_id),
                    celery_task_id=job.celery_task_id,
                )
            if reaped:
                await session.commit()
        return reaped

    async def _run() -> int:
        dispatched = 0
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=STUCK_AFTER_MINUTES)
        await _reap_lost_jobs(cutoff)
        async with AsyncSessionLocal() as session:
            # Find pending docs whose updated_at is old enough (no recent activity)
            pending_docs = (
                await session.execute(
                    select(Document).where(
                        Document.ingest_status == "pending",
                        Document.updated_at < cutoff,
                        Document.storage_uri.isnot(None),
                    )
                )
            ).scalars().all()

            for doc in pending_docs:
                # Skip if there is already an active job for this document
                active = await session.scalar(
                    select(IngestionJob).where(
                        IngestionJob.doc_id == doc.doc_id,
                        IngestionJob.status.in_(("queued", "running", "started")),
                    ).limit(1)
                )
                if active:
                    continue

                job = IngestionJob(
                    job_id=uuid.uuid4(),
                    doc_id=doc.doc_id,
                    document_type=doc.document_type,
                    original_filename=doc.source_file,
                    file_size_bytes=doc.file_size_bytes,
                    factory_id=doc.factory_id,
                    machine_id=doc.machine_id,
                    status="queued",
                )
                session.add(job)
                await session.commit()

                context = {
                    "factory_id": doc.factory_id,
                    "machine_id": doc.machine_id,
                    "document_type": doc.document_type,
                    "document_category": doc.document_category,
                    "language": doc.language,
                    "revision": doc.revision,
                    "revision_sort_key": doc.revision_sort_key,
                    "title": doc.title,
                    "source_file": doc.source_file,
                    "file_hash_sha256": doc.file_hash_sha256,
                }
                result = ingest_document_task.delay(
                    doc_id=str(doc.doc_id),
                    storage_uri=doc.storage_uri,
                    document_type=doc.document_type,
                    document_context=context,
                    job_id=str(job.job_id),
                )
                job.celery_task_id = result.id
                await session.commit()
                dispatched += 1
                log.info(
                    "rescue_pending_dispatched",
                    doc_id=str(doc.doc_id),
                    job_id=str(job.job_id),
                )

        return dispatched

    from spark.core.cache import Cache

    async def _run_and_cleanup() -> int:
        try:
            return await _run()
        finally:
            from spark.core.database import engine
            await engine.dispose()
            await Cache.get().close_for_worker()

    return {"dispatched": asyncio.run(_run_and_cleanup())}
