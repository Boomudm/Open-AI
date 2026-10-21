"""Transform stage — alias resolution, validation, dedup (batch-aware)."""

from __future__ import annotations

from spark.core.metrics import ingest_rows_total
from spark.ingestion.context import IngestContext, TransformStageResult
from spark.ingestion.dedup import should_skip_row_with_meta
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.stages.common import apply_alias_resolution, log_skip
from spark.ingestion.validators import Validator
from spark.services.alias_resolver import AliasResolver
from spark.services.ingest_events import append_ingestion_event
from sqlalchemy.ext.asyncio import AsyncSession


async def transform_batch(
    ctx: IngestContext,
    session: AsyncSession,
    batch: list[ParsedRecord],
    *,
    validator: Validator,
    alias_resolver: AliasResolver,
    seen_chunk_hashes: set[str],
    emit_complete_event: bool = False,
) -> TransformStageResult:
    result = TransformStageResult()
    for rec in batch:
        decision = await should_skip_row_with_meta(
            rec, ctx, session, seen_chunk_hashes=seen_chunk_hashes
        )
        if decision.skip:
            result.rows_skipped += 1
            if decision.is_ocr_skip:
                result.rows_skipped_ocr += 1
            ingest_rows_total.labels(ctx.document_type, "skipped").inc()
            await log_skip(session, ctx.job_id, rec, "duplicate_row", decision.reason)
            continue

        ok, reason, detail = await apply_alias_resolution(
            rec, ctx.config_raw, alias_resolver, session, job_id=ctx.job_id
        )
        if not ok:
            result.rows_skipped += 1
            ingest_rows_total.labels(ctx.document_type, "skipped").inc()
            await log_skip(session, ctx.job_id, rec, reason or "alias_not_resolved", detail)
            continue

        ok, reason, detail = validator.validate(rec, ctx.config_raw, ctx.document_context)
        if not ok:
            result.rows_skipped += 1
            ingest_rows_total.labels(ctx.document_type, "skipped").inc()
            await log_skip(session, ctx.job_id, rec, reason or "validation_format", detail)
            continue

        if rec.route in ("qdrant", "both"):
            result.qdrant_records.append(rec)
        if rec.route in ("postgres", "both"):
            result.postgres_records.append(rec)
        result.rows_ok += 1
        ingest_rows_total.labels(ctx.document_type, "ok").inc()

    if emit_complete_event:
        await append_ingestion_event(
            session,
            job_id=ctx.job_id,
            stage="transform",
            code="transform_complete",
            detail={
                "rows_ok": result.rows_ok,
                "rows_skipped": result.rows_skipped,
                "rows_skipped_ocr": result.rows_skipped_ocr,
            },
        )
    return result


async def run_transform_stage(
    ctx: IngestContext,
    session: AsyncSession,
    parsed_records: list[ParsedRecord],
    *,
    validator: Validator,
    alias_resolver: AliasResolver,
    seen_chunk_hashes: set[str],
) -> TransformStageResult:
    result = await transform_batch(
        ctx,
        session,
        parsed_records,
        validator=validator,
        alias_resolver=alias_resolver,
        seen_chunk_hashes=seen_chunk_hashes,
        emit_complete_event=True,
    )
    return result
