"""Staged ingest pipeline runner (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.core.metrics import ingest_rows_total
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionError, IngestionJob
from spark.ingestion.config_resolver import resolve_ingest_config
from spark.ingestion.context import IngestContext, JobSummary, TrustScanState
from spark.ingestion.errors import (
    PermanentIngestError,
    TransientIngestError,
    classify_exception,
    classify_pipeline_exception,
    permanent_ingest_failure,
)
from spark.ingestion.idempotency import clear_idempotency_key, is_terminal_job_status
from spark.ingestion.ingest_swap import IngestGenerationPlan, abort_staging_ingest
from spark.ingestion.lock import IngestDocLock
from spark.ingestion.parsers import get_parser
from spark.ingestion.reason_codes import ReasonCode
from spark.ingestion.index import PostgresRouter, QdrantRouter
from spark.ingestion.stages.common import expects_qdrant_output
from spark.ingestion.stages.parse_stage import resolve_parser_name
from spark.ingestion.trust import trust_scan_enabled
from spark.ingestion.validators import Validator
from spark.services.alias_resolver import AliasResolver
from spark.services.ingest_events import append_ingestion_event
from spark.services.ingest_progress import ingest_progress_emitter

log = get_logger(__name__)


async def _ensure_job_running(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    doc_id: uuid.UUID,
    document_type: str,
) -> int:
    job_row = await session.get(IngestionJob, job_id)
    if job_row is None:
        session.add(
            IngestionJob(
                job_id=job_id,
                doc_id=doc_id,
                document_type=document_type,
                status="running",
                started_at=datetime.now(tz=timezone.utc),
                attempt_count=1,
            )
        )
        await session.commit()
        return 1
    attempt = int(job_row.attempt_count or 0) + 1
    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == job_id)
        .values(
            status="running",
            started_at=datetime.now(tz=timezone.utc),
            attempt_count=attempt,
            dlq_at=None,
            next_retry_at=None,
        )
    )
    await session.commit()
    return attempt


async def _handle_pipeline_error(
    exc: Exception,
    *,
    ctx: IngestContext,
    summary: JobSummary,
    rows_total: int,
    rows_ok: int,
    rows_skipped: int,
    ingest_plan: IngestGenerationPlan | None,
    chunks_written: int,
    qdrant_router: QdrantRouter,
    qdrant_collection: str | None,
    emit_progress,
) -> None:
    classified = classify_exception(exc)
    reason_code = classified.reason_code
    reason_detail = classified.detail
    error_message = f"{reason_code}: {reason_detail}"[:1000]
    typed = classify_pipeline_exception(exc)

    if ingest_plan is not None and expects_qdrant_output(ctx.config_raw) and chunks_written > 0:
        async with AsyncSessionLocal() as cleanup_session:
            await abort_staging_ingest(
                doc_id=ctx.doc_id,
                plan=ingest_plan,
                qdrant_router=qdrant_router,
                session=cleanup_session,
                collection=qdrant_collection,
            )
            await cleanup_session.commit()

    ingest_rows_total.labels(ctx.document_type, "failed").inc()
    log.error(
        "pipeline_failed",
        doc_id=str(ctx.doc_id),
        reason_code=reason_code,
        retryable=classified.transient,
        exc_info=True,
    )
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as err_session:
        await append_ingestion_event(
            err_session,
            job_id=ctx.job_id,
            stage="error",
            level="error",
            code=reason_code,
            detail={"detail": reason_detail[:500], "transient": classified.transient},
        )
        err_session.add(
            IngestionError(
                job_id=ctx.job_id,
                reason_code=str(reason_code)[:50],
                reason_detail=str(reason_detail)[:2000],
            )
        )
        if isinstance(typed, TransientIngestError):
            await err_session.execute(
                update(IngestionJob)
                .where(IngestionJob.job_id == ctx.job_id)
                .values(
                    status="retrying",
                    rows_total=rows_total,
                    rows_ok=rows_ok,
                    rows_skipped=rows_skipped,
                    last_error_code=str(reason_code)[:50],
                    error_message=error_message,
                    next_retry_at=None,
                )
            )
        elif isinstance(typed, PermanentIngestError):
            if reason_code != ReasonCode.CONTENT_POLICY_BLOCK.value:
                await err_session.execute(
                    update(Document).where(Document.doc_id == ctx.doc_id).values(ingest_status="failed")
                )
            await err_session.execute(
                update(IngestionJob)
                .where(IngestionJob.job_id == ctx.job_id)
                .values(
                    status="failed",
                    dlq_at=None,
                    rows_total=rows_total,
                    rows_ok=rows_ok,
                    rows_skipped=rows_skipped,
                    finished_at=now,
                    last_error_code=str(reason_code)[:50],
                    error_message=error_message,
                    next_retry_at=None,
                )
            )
        else:
            await err_session.execute(
                update(Document).where(Document.doc_id == ctx.doc_id).values(ingest_status="failed")
            )
            await err_session.execute(
                update(IngestionJob)
                .where(IngestionJob.job_id == ctx.job_id)
                .values(
                    status="failed",
                    rows_total=rows_total,
                    rows_ok=rows_ok,
                    rows_skipped=rows_skipped,
                    finished_at=now,
                    last_error_code=str(reason_code)[:50],
                    error_message=error_message,
                    next_retry_at=None,
                )
            )
        terminal_status = (
            "retrying"
            if isinstance(typed, TransientIngestError)
            else "failed"
            if isinstance(typed, PermanentIngestError)
            else "failed"
        )
        if is_terminal_job_status(terminal_status):
            await clear_idempotency_key(err_session, ctx.job_id)
        await err_session.commit()

    if isinstance(typed, TransientIngestError):
        summary.status = "retrying"
        summary.error = error_message
        await emit_progress("retrying", status="retrying")
        raise typed

    summary.status = "failed"
    summary.error = error_message
    await emit_progress("failed", status=summary.status)
    raise typed


async def run_staged_pipeline(
    doc_id: uuid.UUID,
    file_path: Path,
    document_type: str,
    document_context: dict[str, Any],
    job_id: uuid.UUID | None = None,
) -> JobSummary:
    from spark.observability.otel_tracing import record_span_event, set_span_error, start_span

    factory_cfg: dict[str, Any] = {}
    factory_id = document_context.get("factory_id")
    if factory_id:
        from spark.services.factory_config_service import factory_config_service

        async with AsyncSessionLocal() as cfg_session:
            factory_cfg = await factory_config_service.resolve(cfg_session, str(factory_id))

    resolved = resolve_ingest_config(document_type, factory_cfg)
    summary = JobSummary(
        job_id=job_id or uuid.uuid4(),
        doc_id=doc_id,
        status="running",
    )

    async with AsyncSessionLocal() as boot_session:
        attempt = await _ensure_job_running(
            boot_session,
            job_id=summary.job_id,
            doc_id=doc_id,
            document_type=document_type,
        )

    ctx = IngestContext.build(
        doc_id=doc_id,
        job_id=summary.job_id,
        document_type=document_type,
        file_path=file_path,
        document_context=document_context,
        resolved=resolved,
        job_attempt_count=attempt,
    )
    ctx.document_context["config_hash"] = resolved.config_hash()
    trust_state = TrustScanState(enabled=trust_scan_enabled())

    log.info(
        "resolved_ingest_config",
        document_type=document_type,
        config_hash=resolved.config_hash(),
        chunk_profile=resolved.chunking.profile,
    )

    parser = get_parser(resolve_parser_name(ctx))
    validator = Validator()
    qdrant_router = QdrantRouter()
    postgres_router = PostgresRouter()
    alias_resolver = AliasResolver()
    rows_total = 0

    # rows_total grows WHILE parsing streams (it is "rows parsed so far"),
    # so done/total is a misleadingly high, jittery ratio mid-run — the bar
    # jumped up and down and parked near 97% for minutes. Scale the running
    # ratio into a 5–90 band and never let the emitted percent move backward;
    # 100 is reserved for terminal states.
    last_emitted_percent = 0

    async def emit_progress(stage: str, status: str | None = None) -> None:
        nonlocal last_emitted_percent
        total = max(summary.rows_total, 1)
        done = summary.rows_ok + summary.rows_skipped
        if status in ("completed", "partial", "failed", "dlq", "pending_release"):
            percent = 100
        else:
            percent = 5 + round(min(1.0, done / total) * 85)
            percent = max(percent, last_emitted_percent)
        last_emitted_percent = percent
        await ingest_progress_emitter.emit(
            job_id=str(summary.job_id),
            factory_id=ctx.factory_id,
            percent=percent,
            rows_ok=summary.rows_ok,
            rows_total=summary.rows_total,
            stage=stage,
            status=status or summary.status,
        )

    await emit_progress("starting", status="running")

    with start_span(
        "ingest.pipeline",
        doc_id=str(doc_id),
        document_type=document_type,
        factory_id=factory_id or "",
    ) as ingest_span:
        async with AsyncSessionLocal() as session:
            async with IngestDocLock(session) as doc_lock:
                if not await doc_lock.acquire(doc_id, summary.job_id):
                    raise permanent_ingest_failure(
                        ReasonCode.DUPLICATE_JOB_IN_PROGRESS,
                        f"doc_id={doc_id} already ingesting",
                    )
                try:
                    from spark.ingestion.orchestrator import run_streaming_pipeline
                    summary = await run_streaming_pipeline(
                        ctx,
                        session,
                        parser=parser,
                        trust_state=trust_state,
                        validator=validator,
                        alias_resolver=alias_resolver,
                        qdrant_router=qdrant_router,
                        postgres_router=postgres_router,
                        resolved=resolved,
                        summary=summary,
                        emit_progress=emit_progress,
                    )
                    rows_total = summary.rows_total
                    record_span_event(ingest_span, "pipeline_complete", rows_ok=summary.rows_ok, rows_total=rows_total)
                except Exception as exc:
                    set_span_error(ingest_span, exc)
                    await session.rollback()
                    await _handle_pipeline_error(
                        exc,
                        ctx=ctx,
                        summary=summary,
                        rows_total=summary.rows_total or rows_total,
                        rows_ok=summary.rows_ok,
                        rows_skipped=summary.rows_skipped,
                        ingest_plan=ctx.ingest_plan,
                        chunks_written=ctx.chunks_written,
                        qdrant_router=qdrant_router,
                        qdrant_collection=ctx.qdrant_collection,
                        emit_progress=emit_progress,
                    )

    return summary
