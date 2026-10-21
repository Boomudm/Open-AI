"""Streaming ingest orchestrator — bounded batches with micro-commits."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.ingestion.budget import ResourceBudgetTracker, budget_from_config
from spark.ingestion.context import (
    IngestContext,
    IndexStageResult,
    JobSummary,
    TransformStageResult,
    TrustScanState,
)
from spark.ingestion.document_accumulator import DocumentAccumulator
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.idempotency import clear_idempotency_key
from spark.ingestion.ingest_swap import IngestGenerationPlan, abort_staging_ingest, resolve_ingest_generation
from spark.ingestion.index import PostgresRouter, QdrantRouter
from spark.ingestion.parsers.base import ParserPlugin
from spark.ingestion.stages.common import expects_qdrant_output, qdrant_collection
from spark.ingestion.stages.finalize_stage import run_finalize_stage
from spark.ingestion.stages.index_stage import index_batch
from spark.ingestion.stages.parse_stage import parse_batched
from spark.ingestion.stages.transform_stage import transform_batch
from spark.ingestion.stages.trust_stage import (
    TrustStageOutcome,
    apply_post_chunk_policy,
    finalize_quarantine,
    trust_batch,
)
from spark.ingestion.trust import trust_scanner
from spark.ingestion.validators import Validator
from spark.services.alias_resolver import AliasResolver
from spark.services.ingest_events import append_ingestion_event

log = get_logger(__name__)

DEFAULT_BATCH_SIZE = 64


@asynccontextmanager
async def stage_span(name: str):
    log.debug("ingest_stage_start", stage=name)
    try:
        yield
    finally:
        log.debug("ingest_stage_end", stage=name)


async def _abort_staging_if_needed(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    ingest_plan: IngestGenerationPlan | None,
    qdrant_router: QdrantRouter,
) -> None:
    if (
        ingest_plan is not None
        and expects_qdrant_output(ctx.config_raw)
        and ctx.chunks_written > 0
    ):
        await abort_staging_ingest(
            doc_id=ctx.doc_id,
            plan=ingest_plan,
            qdrant_router=qdrant_router,
            session=session,
            collection=ctx.qdrant_collection,
        )


async def _drain_parse_into_accumulator(
    parse_iter,
    accumulator: DocumentAccumulator,
) -> int:
    rows_total = accumulator.record_count()
    async for batch, batch_rows_total in parse_iter:
        accumulator.append_batch(batch)
        rows_total = batch_rows_total
    return rows_total


async def _handle_quarantine_exit(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    accumulator: DocumentAccumulator,
    rows_total: int,
    trust_state: TrustScanState,
    trust_outcome: TrustStageOutcome,
    ingest_plan: IngestGenerationPlan | None,
    qdrant_router: QdrantRouter,
    summary: JobSummary,
    emit_progress: Callable[[str, str | None], Awaitable[None]],
) -> JobSummary:
    await _abort_staging_if_needed(ctx, session, ingest_plan=ingest_plan, qdrant_router=qdrant_router)
    if accumulator.record_count() != rows_total:
        raise PermanentIngestError(
            "quarantine_incomplete",
            f"quarantine artifact records={accumulator.record_count()} rows_total={rows_total}",
        )
    outcome = await finalize_quarantine(
        ctx,
        session,
        accumulator=accumulator,
        rows_total=rows_total,
        trust_state=trust_state,
        trust_outcome=trust_outcome,
    )
    await clear_idempotency_key(session, ctx.job_id)
    await session.commit()
    summary.status = outcome.summary_status or "pending_release"
    summary.rows_total = rows_total
    await emit_progress("quarantined", summary.status)
    return summary


async def run_streaming_pipeline(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    parser: ParserPlugin,
    trust_state: TrustScanState,
    validator: Validator,
    alias_resolver: AliasResolver,
    qdrant_router: QdrantRouter,
    postgres_router: PostgresRouter,
    resolved: Any,
    summary: JobSummary,
    emit_progress: Callable[[str, str | None], Awaitable[None]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> JobSummary:
    budget = ResourceBudgetTracker(budget_from_config(ctx.config_raw))
    ctx.budget = budget
    seen_chunk_hashes: set[str] = set()
    ingest_plan: IngestGenerationPlan | None = None
    qdrant_collection_name: str | None = None
    accumulated = TransformStageResult()
    index_result = IndexStageResult()
    rows_total = 0
    generation_resolved = False
    policy_scan_emitted = False
    accumulator = DocumentAccumulator(ctx.doc_id)

    parse_iter = parse_batched(
        ctx,
        session,
        parser,
        budget=budget,
        batch_size=batch_size,
    ).__aiter__()

    while True:
        try:
            batch, batch_rows_total = await parse_iter.__anext__()
        except StopAsyncIteration:
            break

        rows_total = batch_rows_total
        summary.rows_total = rows_total
        accumulator.append_batch(batch)

        if not policy_scan_emitted:
            await emit_progress("policy_scan")
            policy_scan_emitted = True

        async with stage_span("trust"):
            trust_outcome = await trust_batch(
                ctx,
                session,
                batch,
                rows_total=rows_total,
                scanner=trust_scanner,
                trust_state=trust_state,
                accumulator=accumulator,
            )
        if trust_outcome.kind == "quarantine":
            rows_total = await _drain_parse_into_accumulator(parse_iter, accumulator)
            summary.rows_total = rows_total
            return await _handle_quarantine_exit(
                ctx,
                session,
                accumulator=accumulator,
                rows_total=rows_total,
                trust_state=trust_state,
                trust_outcome=trust_outcome,
                ingest_plan=ingest_plan,
                qdrant_router=qdrant_router,
                summary=summary,
                emit_progress=emit_progress,
            )

        if not generation_resolved and expects_qdrant_output(resolved):
            ingest_plan = await resolve_ingest_generation(session, ctx.doc_id)
            ctx.staging_generation = ingest_plan.staging
            ctx.is_reingest = ingest_plan.is_reingest
            ctx.ingest_plan = ingest_plan
            qdrant_collection_name = qdrant_collection(resolved, ctx.document_context)
            ctx.qdrant_collection = qdrant_collection_name
            generation_resolved = True

        async with stage_span("transform"):
            transform_result = await transform_batch(
                ctx,
                session,
                batch,
                validator=validator,
                alias_resolver=alias_resolver,
                seen_chunk_hashes=seen_chunk_hashes,
            )

        if transform_result.qdrant_records:
            post_outcome = await apply_post_chunk_policy(
                ctx,
                session,
                transform_result.qdrant_records,
                rows_total=rows_total,
                scanner=trust_scanner,
                trust_state=trust_state,
                accumulator=accumulator,
            )
            if post_outcome is not None and post_outcome.kind == "quarantine":
                rows_total = await _drain_parse_into_accumulator(parse_iter, accumulator)
                summary.rows_total = rows_total
                return await _handle_quarantine_exit(
                    ctx,
                    session,
                    accumulator=accumulator,
                    rows_total=rows_total,
                    trust_state=trust_state,
                    trust_outcome=post_outcome,
                    ingest_plan=ingest_plan,
                    qdrant_router=qdrant_router,
                    summary=summary,
                    emit_progress=emit_progress,
                )

        for record in transform_result.qdrant_records:
            page = record.payload.get("page")
            if page is not None:
                try:
                    ctx.indexed_pages.add(int(page))
                except (TypeError, ValueError):
                    pass

        accumulated.rows_ok += transform_result.rows_ok
        accumulated.rows_skipped += transform_result.rows_skipped
        accumulated.rows_skipped_ocr += transform_result.rows_skipped_ocr
        summary.rows_ok = accumulated.rows_ok
        summary.rows_skipped = accumulated.rows_skipped
        summary.rows_skipped_ocr = accumulated.rows_skipped_ocr

        async with stage_span("index"):
            chunks_written = await index_batch(
                ctx,
                session,
                transform_result,
                qdrant_router=qdrant_router,
                postgres_router=postgres_router,
                ingest_plan=ingest_plan,
                rows_total=rows_total,
                rows_ok=accumulated.rows_ok,
                rows_skipped=accumulated.rows_skipped,
            )
        index_result.chunks_written += chunks_written
        ctx.chunks_written = index_result.chunks_written
        await session.commit()
        await emit_progress("index", "running")

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="transform",
        code="transform_complete",
        detail={
            "rows_ok": accumulated.rows_ok,
            "rows_skipped": accumulated.rows_skipped,
            "rows_skipped_ocr": accumulated.rows_skipped_ocr,
            "streaming": True,
        },
    )
    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="index",
        code="index_complete",
        detail={"chunks_written": index_result.chunks_written, "streaming": True},
    )

    summary = await run_finalize_stage(
        ctx,
        session,
        summary,
        accumulated,
        index_result,
        trust_state=trust_state,
        ingest_plan=ingest_plan,
        qdrant_router=qdrant_router,
        qdrant_collection=qdrant_collection_name,
        rows_total=rows_total,
        document_accumulator=accumulator,
    )
    await clear_idempotency_key(session, ctx.job_id)
    await emit_progress("done", summary.status)
    return summary
