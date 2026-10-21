"""Worker-crash recovery: job rows stranded in queued/running whose Celery task
no longer exists must be reaped so the pending-doc rescuer can requeue the
document — previously the "active job" guard treated those corpses as live and
the document never recovered."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob


def _run(coro):
    return asyncio.run(coro)


async def _insert_doc_and_job(doc_id, job_id, *, with_doc: bool, status: str) -> None:
    old = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    async with AsyncSessionLocal() as session:
        if with_doc:
            session.add(
                Document(
                    doc_id=doc_id,
                    factory_id="F-01",
                    document_type="machine_manual",
                    document_category="knowledge",
                    title="crash test doc",
                    source_file="crash.pdf",
                    storage_uri="file:///tmp/crash.pdf",
                    ingest_status="pending",
                    created_at=old,
                    updated_at=old,
                )
            )
        session.add(
            IngestionJob(
                job_id=job_id,
                doc_id=doc_id if with_doc else None,
                document_type="machine_manual",
                status=status,
                celery_task_id="dead-task-id",
                created_at=old,
            )
        )
        await session.commit()


async def _cleanup(doc_id, *_job_ids) -> None:
    async with AsyncSessionLocal() as session:
        for job in (
            await session.execute(select(IngestionJob).where(IngestionJob.doc_id == doc_id))
        ).scalars():
            await session.delete(job)
        for job_id in _job_ids:
            job = await session.get(IngestionJob, job_id)
            if job is not None:
                await session.delete(job)
        doc = await session.get(Document, doc_id)
        if doc is not None:
            await session.delete(doc)
        await session.commit()


async def _job_status(job_id) -> str | None:
    async with AsyncSessionLocal() as session:
        job = await session.get(IngestionJob, job_id)
        return job.status if job else None


async def _queued_jobs_for(doc_id) -> int:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.doc_id == doc_id, IngestionJob.status == "queued"
                )
            )
        ).scalars().all()
        return len(rows)


def test_reaper_marks_dead_jobs_lost_and_doc_requeues(monkeypatch) -> None:
    import spark.workers.tasks as tasks_mod

    doc_id, job_id = uuid.uuid4(), uuid.uuid4()
    _run(_insert_doc_and_job(doc_id, job_id, with_doc=True, status="running"))
    try:
        # No worker/broker knows this task id → it is dead.
        monkeypatch.setattr(tasks_mod, "_known_celery_task_ids", lambda: set())

        class _FakeResult:
            id = "rescued-task-id"

        monkeypatch.setattr(
            tasks_mod.ingest_document_task, "delay", lambda **kw: _FakeResult()
        )

        outcome = tasks_mod.rescue_stuck_pending_task()
        assert outcome["dispatched"] >= 1

        assert _run(_job_status(job_id)) == "lost"
        assert _run(_queued_jobs_for(doc_id)) >= 1, (
            "document with a reaped job must be redispatched"
        )
    finally:
        _run(_cleanup(doc_id, job_id))


def test_reaper_skips_when_celery_state_unknown(monkeypatch) -> None:
    """If no worker responds, the reaper must not guess — a healthy long-running
    job would otherwise be killed during a transient inspect outage."""
    import spark.workers.tasks as tasks_mod

    doc_id, job_id = uuid.uuid4(), uuid.uuid4()
    _run(_insert_doc_and_job(doc_id, job_id, with_doc=False, status="running"))
    try:
        monkeypatch.setattr(tasks_mod, "_known_celery_task_ids", lambda: None)
        monkeypatch.setattr(
            tasks_mod.ingest_document_task, "delay", lambda **kw: None
        )
        tasks_mod.rescue_stuck_pending_task()
        assert _run(_job_status(job_id)) == "running"
    finally:
        _run(_cleanup(doc_id, job_id))