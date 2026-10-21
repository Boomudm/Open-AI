"""Finalize stage — saga swap, registry, notifications."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.core.metrics import ingest_partial_swap_total
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.ingestion.context import IngestContext, IndexStageResult, JobSummary, TransformStageResult, TrustScanState
from spark.ingestion.document_accumulator import DocumentAccumulator
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.idempotency import clear_idempotency_key
from spark.ingestion.index.qdrant_writer import QdrantRouter
from spark.ingestion.index.saga import IngestIndexSaga
from spark.ingestion.index.drift_errors import IndexDriftError
from spark.ingestion.ingest_swap import IngestGenerationPlan, abort_staging_ingest
from spark.ingestion.job_reliability import skip_breakdown_by_reason
from spark.ingestion.quality.slo import build_quality_report, evaluate_slos
from spark.ingestion.quality_slos import enforce_safety_swap_policy, safety_document_types
from spark.ingestion.stages.common import (
    document_registry_updates,
    empty_index_failure,
    expects_qdrant_output,
    resolve_job_status,
)
from spark.ingestion.stages.trust_stage import apply_finalize_document_trust, finalize_quarantine
from spark.ingestion.trust import trust_scanner
from spark.services.ingest_events import append_ingestion_event

log = get_logger(__name__)


async def notify_partial_job(
    *,
    factory_id: str | None,
    job_id: uuid.UUID,
    doc_id: uuid.UUID,
    document_context: dict[str, Any],
    rows_ok: int,
    rows_skipped: int,
) -> None:
    if not factory_id or rows_skipped <= 0:
        return
    breakdown = await skip_breakdown_by_reason(job_id)
    lines = [f"{code}: {count}" for code, count in sorted(breakdown.items())]
    body = (
        f"Ingest partial — {rows_ok} rows ok, {rows_skipped} skipped.\n"
        f"Skip breakdown: {', '.join(lines) if lines else 'none'}"
    )
    from spark.services.notification_dispatch_service import notification_dispatch_service

    try:
        async with AsyncSessionLocal() as notify_session:
            await notification_dispatch_service.notify_factory(
                notify_session,
                factory_id=str(factory_id),
                event_type="ingest_partial",
                subject=f"Ingest partial: {document_context.get('source_file') or doc_id}",
                body=body,
                context={
                    "job_id": str(job_id),
                    "doc_id": str(doc_id),
                    "rows_ok": rows_ok,
                    "rows_skipped": rows_skipped,
                    "skip_breakdown": breakdown,
                },
            )
            await notify_session.commit()
    except Exception as notify_exc:
        log.warning("ingest_partial_notify_failed", error=str(notify_exc)[:200])


async def notify_quality_slo_breach(
    *,
    factory_id: str | None,
    job_id: uuid.UUID,
    doc_id: uuid.UUID,
    document_context: dict[str, Any],
    detail: str,
) -> None:
    if not factory_id:
        return
    from spark.services.notification_dispatch_service import notification_dispatch_service

    try:
        async with AsyncSessionLocal() as notify_session:
            await notification_dispatch_service.notify_factory(
                notify_session,
                factory_id=str(factory_id),
                event_type="ingest_quality_slo_breach",
                subject=f"Ingest quality SLO breach: {document_context.get('source_file') or doc_id}",
                body=detail,
                context={
                    "job_id": str(job_id),
                    "doc_id": str(doc_id),
                    "detail": detail,
                },
            )
            await notify_session.commit()
    except Exception as notify_exc:
        log.warning("ingest_quality_slo_notify_failed", error=str(notify_exc)[:200])


async def run_finalize_stage(
    ctx: IngestContext,
    session: AsyncSession,
    summary: JobSummary,
    transform_result: TransformStageResult,
    index_result: IndexStageResult,
    *,
    trust_state: TrustScanState,
    ingest_plan: IngestGenerationPlan | None,
    qdrant_router: QdrantRouter,
    qdrant_collection: str | None,
    rows_total: int,
    document_accumulator: DocumentAccumulator | None = None,
) -> JobSummary:
    if failure := empty_index_failure(
        ctx.config_raw,
        rows_total=rows_total,
        chunks_written=index_result.chunks_written,
    ):
        raise PermanentIngestError(*failure)

    if document_accumulator is not None:
        trust_outcome = await apply_finalize_document_trust(
            ctx,
            session,
            accumulator=document_accumulator,
            rows_total=rows_total,
            trust_state=trust_state,
            scanner=trust_scanner,
        )
        if trust_outcome is not None and trust_outcome.kind == "quarantine":
            if (
                ingest_plan is not None
                and expects_qdrant_output(ctx.config_raw)
                and index_result.chunks_written > 0
            ):
                await abort_staging_ingest(
                    doc_id=ctx.doc_id,
                    plan=ingest_plan,
                    qdrant_router=qdrant_router,
                    session=session,
                    collection=qdrant_collection,
                )
            await finalize_quarantine(
                ctx,
                session,
                accumulator=document_accumulator,
                rows_total=rows_total,
                trust_state=trust_state,
                trust_outcome=trust_outcome,
            )
            await clear_idempotency_key(session, ctx.job_id)
            await session.commit()
            summary.status = "pending_release"
            summary.rows_total = rows_total
            return summary

    registry_updates = document_registry_updates(
        ctx.document_context,
        index_result.chunks_written,
        transform_result.rows_skipped,
        transform_result.rows_skipped_ocr,
        trust_state=trust_state if trust_state.enabled else None,
    )
    job_status = resolve_job_status(
        transform_result.rows_ok,
        transform_result.rows_skipped,
        transform_result.rows_skipped_ocr,
    )

    if slo_failure := enforce_safety_swap_policy(
        document_type=ctx.document_type,
        job_status=job_status,
        rows_ok=transform_result.rows_ok,
        rows_skipped=transform_result.rows_skipped,
        rows_skipped_ocr=transform_result.rows_skipped_ocr,
        rows_total=rows_total,
        document_context=ctx.document_context,
        parse_warnings=ctx.parse_warnings,
        indexed_pages=ctx.indexed_pages,
    ):
        await notify_quality_slo_breach(
            factory_id=ctx.factory_id,
            job_id=ctx.job_id,
            doc_id=ctx.doc_id,
            document_context=ctx.document_context,
            detail=slo_failure[1],
        )
        raise PermanentIngestError(*slo_failure)

    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == ctx.job_id)
        .values(
            status=job_status,
            rows_total=rows_total,
            rows_ok=transform_result.rows_ok,
            rows_skipped=transform_result.rows_skipped,
            rows_skipped_ocr=transform_result.rows_skipped_ocr,
            finished_at=datetime.now(tz=timezone.utc),
            last_error_code=None,
            error_message=None,
        )
    )

    saga: IngestIndexSaga | None = None
    if ingest_plan is not None and expects_qdrant_output(ctx.config_raw):
        quality_report = build_quality_report(
            document_context=ctx.document_context,
            transform=transform_result,
            rows_total=rows_total,
            parse_warnings=ctx.parse_warnings,
            indexed_pages=ctx.indexed_pages,
        )
        partial_allowed = evaluate_slos(quality_report, ctx.document_type).partial_swap_allowed
        if job_status == "partial":
            if not partial_allowed:
                raise PermanentIngestError(
                    "quality_slo_breach",
                    f"partial ingest not allowed for document type {ctx.document_type}",
                )
            swap_reason = "swap_partial_explicit"
            ingest_partial_swap_total.labels(document_type=ctx.document_type).inc()
        else:
            swap_reason = "committed"
        saga = IngestIndexSaga(
            doc_id=ctx.doc_id,
            plan=ingest_plan,
            qdrant_router=qdrant_router,
            collection=qdrant_collection,
        )
        try:
            await saga.verify_staging(
                session,
                pg_count=index_result.chunks_written,
                document_type=ctx.document_type,
            )
            from spark.ingestion.eval_gate import require_swap_eval_token

            await require_swap_eval_token(ctx, session)
            await saga.commit_swap(
                session,
                chunks_count=index_result.chunks_written,
                document_updates=registry_updates,
                reason_code=swap_reason,
                factory_id=str(ctx.factory_id) if ctx.factory_id else None,
                attempt_count=ctx.job_attempt_count,
                policy_version=trust_state.version if trust_state.enabled else None,
            )
            if job_status == "partial":
                await append_ingestion_event(
                    session,
                    job_id=ctx.job_id,
                    stage="finalize",
                    code="swap_partial_explicit",
                    detail={
                        "rows_ok": transform_result.rows_ok,
                        "rows_skipped": transform_result.rows_skipped,
                        "document_type": ctx.document_type,
                    },
                )
            await saga.schedule_purge(session)
        except IndexDriftError as exc:
            await saga.abort(session)
            await session.execute(
                update(Document)
                .where(Document.doc_id == ctx.doc_id)
                .values(
                    ingest_status="index_drift",
                    quarantine_reason=exc.reason_detail,
                )
            )
            raise PermanentIngestError(exc.reason_code, exc.reason_detail) from exc
    else:
        await session.execute(
            update(Document).where(Document.doc_id == ctx.doc_id).values(**registry_updates)
        )

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="finalize",
        code=f"job_{job_status}",
        detail={
            "rows_ok": transform_result.rows_ok,
            "rows_skipped": transform_result.rows_skipped,
            "chunks_written": index_result.chunks_written,
        },
    )
    await session.commit()

    summary.status = job_status
    summary.rows_ok = transform_result.rows_ok
    summary.rows_skipped = transform_result.rows_skipped
    summary.rows_skipped_ocr = transform_result.rows_skipped_ocr
    summary.rows_total = rows_total

    if job_status == "partial" and ctx.document_type not in safety_document_types():
        await notify_partial_job(
            factory_id=ctx.factory_id,
            job_id=ctx.job_id,
            doc_id=ctx.doc_id,
            document_context=ctx.document_context,
            rows_ok=transform_result.rows_ok,
            rows_skipped=transform_result.rows_skipped,
        )

    ocr_min = ctx.document_context.get("ocr_confidence_min")
    if ctx.factory_id and ocr_min is not None and float(ocr_min) < settings.ocr_confidence_alert_min:
        from spark.services.notification_dispatch_service import notification_dispatch_service

        try:
            async with AsyncSessionLocal() as notify_session:
                await notification_dispatch_service.notify_factory(
                    notify_session,
                    factory_id=str(ctx.factory_id),
                    event_type="ocr_low_confidence",
                    subject=f"OCR confidence ต่ำ ({ocr_min}%)",
                    body=(
                        f"เอกสาร {ctx.document_context.get('original_filename') or ctx.doc_id} "
                        f"มี OCR confidence ต่ำกว่า {settings.ocr_confidence_alert_min}% "
                        f"(ได้ {ocr_min}%) — ควรตรวจสอบหรือ re-scan"
                    ),
                    context={
                        "job_id": str(ctx.job_id),
                        "doc_id": str(ctx.doc_id),
                        "ocr_confidence_min": float(ocr_min),
                    },
                )
                await notify_session.commit()
        except Exception as notify_exc:
            log.warning("ocr_low_confidence_notify_failed", error=str(notify_exc)[:120])

    if settings.qa_cache_enabled:
        from spark.services.qa_cache_service import qa_cache_service

        async with AsyncSessionLocal() as cache_session:
            await qa_cache_service.invalidate_by_doc_id(cache_session, ctx.doc_id)
            await cache_session.commit()

    return summary
