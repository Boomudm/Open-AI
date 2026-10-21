from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.config import settings
from spark.core.database import get_session
from spark.core.security import enforce_factory_access, enforce_write_factory, get_principal
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionError, IngestionJob
from spark.schemas.documents import IngestionErrorOut, IngestionJobOut
from spark.services.streams.connection_governor import connection_governor, ensure_sse_connection
from spark.services.streams.disconnect import track_disconnect
from spark.services.streams.ingest_stream_service import ingest_stream_service

router = APIRouter(prefix="/ingest/jobs", tags=["Ingestion"])


def _duration_seconds(
    started_at: datetime | None,
    finished_at: datetime | None,
) -> float | None:
    if started_at is None:
        return None
    end = finished_at or datetime.now(tz=timezone.utc)
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return max(0.0, round((end - start).total_seconds(), 3))


def _progress_percent(job: IngestionJob) -> int:
    status = (job.status or "").lower()
    if status in ("completed", "partial", "failed", "dlq", "pending_release"):
        return 100
    total = int(job.rows_total or 0)
    if total <= 0:
        # Show activity indicator so the UI doesn't display a stuck 0%
        if status in ("running", "started"):
            return 15
        if status == "queued":
            return 5
        return 0
    done = int(job.rows_ok or 0) + int(job.rows_skipped or 0)
    # Same 5-90 running band as the SSE emitter (see stages/runner.py):
    # rows_total is "rows parsed so far" while the job streams, so the raw
    # ratio overstates progress and wobbles as the denominator grows.
    return max(5, min(90, 5 + round(min(1.0, done / total) * 85)))


def _job_to_out(
    job: IngestionJob,
    doc: Document | None = None,
    *,
    error_count: int = 0,
    last_error_code: str | None = None,
    last_error_detail: str | None = None,
) -> IngestionJobOut:
    return IngestionJobOut(
        job_id=job.job_id,
        doc_id=job.doc_id,
        document_type=job.document_type,
        original_filename=job.original_filename or (doc.source_file if doc else None),
        file_size_bytes=(
            job.file_size_bytes
            if job.file_size_bytes is not None
            else (doc.file_size_bytes if doc else None)
        ),
        factory_id=job.factory_id or (doc.factory_id if doc else None),
        machine_id=job.machine_id or (doc.machine_id if doc else None),
        status=job.status,
        rows_total=job.rows_total,
        rows_ok=job.rows_ok,
        rows_skipped=job.rows_skipped,
        progress_percent=_progress_percent(job),
        chunks_count=doc.chunks_count if doc else 0,
        page_count=doc.page_count if doc else None,
        document_ingest_status=doc.ingest_status if doc else None,
        error_count=error_count,
        last_error_code=last_error_code,
        last_error_detail=last_error_detail,
        duration_seconds=_duration_seconds(job.started_at, job.finished_at),
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        error_message=job.error_message,
        attempt_count=int(job.attempt_count or 0),
        dlq_at=job.dlq_at,
        next_retry_at=job.next_retry_at,
    )


def _latest_error_subqueries():
    error_count = (
        select(func.count(IngestionError.error_id))
        .where(IngestionError.job_id == IngestionJob.job_id)
        .correlate(IngestionJob)
        .scalar_subquery()
    )
    last_error_code = (
        select(IngestionError.reason_code)
        .where(IngestionError.job_id == IngestionJob.job_id)
        .order_by(IngestionError.created_at.desc(), IngestionError.error_id.desc())
        .limit(1)
        .correlate(IngestionJob)
        .scalar_subquery()
    )
    last_error_detail = (
        select(IngestionError.reason_detail)
        .where(IngestionError.job_id == IngestionJob.job_id)
        .order_by(IngestionError.created_at.desc(), IngestionError.error_id.desc())
        .limit(1)
        .correlate(IngestionJob)
        .scalar_subquery()
    )
    return error_count, last_error_code, last_error_detail


def _job_factory_id(job: IngestionJob, doc: Document | None) -> str | None:
    return job.factory_id or (doc.factory_id if doc else None)


def _enforce_job_access(request: Request, job: IngestionJob, doc: Document | None) -> None:
    p = get_principal(request)
    factory_id = _job_factory_id(job, doc)
    enforce_factory_access(p, factory_id, "read")
    if factory_id is None and not p.is_admin and settings.effective_auth_required:
        raise HTTPException(403, "factory scope required for ingestion job access")


@router.get("", response_model=list[IngestionJobOut], responses=READ_ERRORS)
async def list_jobs(
    request: Request,
    status: str | None = None,
    factory_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_factory_access(p, factory_id, "read")
    error_count, last_error_code, last_error_detail = _latest_error_subqueries()
    stmt = (
        select(
            IngestionJob,
            Document,
            error_count.label("error_count"),
            last_error_code.label("last_error_code"),
            last_error_detail.label("last_error_detail"),
        )
        .outerjoin(Document, IngestionJob.doc_id == Document.doc_id)
    )
    if status:
        stmt = stmt.where(IngestionJob.status == status)
    if factory_id:
        stmt = stmt.where(
            or_(
                IngestionJob.factory_id == factory_id,
                Document.factory_id == factory_id,
            )
        )
    stmt = stmt.order_by(IngestionJob.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()
    return [
        _job_to_out(
            job,
            doc,
            error_count=int(row_error_count or 0),
            last_error_code=row_last_error_code,
            last_error_detail=row_last_error_detail,
        )
        for job, doc, row_error_count, row_last_error_code, row_last_error_detail in rows
    ]


@router.get("/{job_id}", response_model=IngestionJobOut, responses=READ_ERRORS)
async def get_job(
    job_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    error_count, last_error_code, last_error_detail = _latest_error_subqueries()
    row = (
        await session.execute(
            select(
                IngestionJob,
                Document,
                error_count.label("error_count"),
                last_error_code.label("last_error_code"),
                last_error_detail.label("last_error_detail"),
            )
            .outerjoin(Document, IngestionJob.doc_id == Document.doc_id)
            .where(IngestionJob.job_id == job_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(404, "job not found")
    job, doc, row_error_count, row_last_error_code, row_last_error_detail = row
    _enforce_job_access(request, job, doc)
    return _job_to_out(
        job,
        doc,
        error_count=int(row_error_count or 0),
        last_error_code=row_last_error_code,
        last_error_detail=row_last_error_detail,
    )


@router.get("/{job_id}/errors", response_model=list[IngestionErrorOut], responses=READ_ERRORS)
async def get_job_errors(
    job_id: UUID,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(
            select(IngestionJob, Document)
            .outerjoin(Document, IngestionJob.doc_id == Document.doc_id)
            .where(IngestionJob.job_id == job_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(404, "job not found")
    job, doc = row
    _enforce_job_access(request, job, doc)

    stmt = (
        select(IngestionError)
        .where(IngestionError.job_id == job_id)
        .order_by(IngestionError.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await session.execute(stmt)).scalars().all()


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: UUID,
    request: Request,
):
    from spark.core.database import StreamSessionLocal

    p = get_principal(request)
    user_id = p.user_id or "anonymous"
    ensure_sse_connection(user_id=user_id, channel="ingest_job")

    try:
        async with StreamSessionLocal() as session:
            row = (
                await session.execute(
                    select(IngestionJob, Document)
                    .outerjoin(Document, IngestionJob.doc_id == Document.doc_id)
                    .where(IngestionJob.job_id == job_id)
                )
            ).one_or_none()
            if not row:
                raise HTTPException(404, "job not found")
            job, doc = row
            _enforce_job_access(request, job, doc)
            await session.commit()
    except HTTPException:
        connection_governor.release(user_id=user_id, channel="ingest_job")
        raise

    async def _generate():
        try:
            async for event in track_disconnect(
                request,
                ingest_stream_service.stream_job(job_id),
            ):
                yield event
        finally:
            connection_governor.release(user_id=user_id, channel="ingest_job")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{job_id}/retry", response_model=IngestionJobOut, responses=WRITE_ERRORS)
async def retry_job(
    job_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Re-queue a failed or DLQ ingest job for another attempt."""
    row = (
        await session.execute(
            select(IngestionJob, Document)
            .outerjoin(Document, IngestionJob.doc_id == Document.doc_id)
            .where(IngestionJob.job_id == job_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(404, "job not found")
    job, doc = row
    factory_id = _job_factory_id(job, doc)
    p = get_principal(request)
    enforce_write_factory(p, factory_id)
    if (job.status or "").lower() not in ("dlq", "failed"):
        raise HTTPException(409, f"job status {job.status!r} is not retryable")

    if doc is None or not doc.storage_uri:
        raise HTTPException(409, "document storage is unavailable for retry")

    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == job_id)
        .values(
            status="queued",
            dlq_at=None,
            finished_at=None,
            error_message=None,
            next_retry_at=None,
            last_error_code=None,
        )
    )
    await session.execute(delete(IngestionError).where(IngestionError.job_id == job_id))
    if doc:
        await session.execute(
            update(Document).where(Document.doc_id == doc.doc_id).values(ingest_status="pending")
        )
    await session.commit()

    context = {
        "factory_id": doc.factory_id if doc else job.factory_id,
        "machine_id": doc.machine_id if doc else job.machine_id,
        "document_type": job.document_type,
        "document_category": doc.document_category if doc else None,
        "language": "th",
        "revision": doc.revision if doc else None,
        "title": doc.title if doc else job.original_filename,
        "source_file": doc.source_file if doc else job.original_filename,
    }

    from spark.workers.tasks import ingest_document_task

    async_result = ingest_document_task.delay(
        doc_id=str(job.doc_id),
        storage_uri=doc.storage_uri,
        document_type=job.document_type,
        document_context=context,
        job_id=str(job.job_id),
    )
    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == job_id)
        .values(celery_task_id=async_result.id)
    )
    await session.commit()

    job = await session.get(IngestionJob, job_id)
    doc = await session.get(Document, job.doc_id) if job and job.doc_id else doc
    return _job_to_out(job, doc)
