"""Index stage — Qdrant and Postgres writers (batch-aware)."""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.ingestion import IngestionJob
from spark.ingestion.context import IngestContext, IndexStageResult, TransformStageResult
from spark.ingestion.ingest_swap import IngestGenerationPlan
from spark.ingestion.index import PostgresRouter, QdrantRouter
from spark.services.ingest_events import append_ingestion_event

QDRANT_FLUSH_SIZE = 32


async def index_batch(
    ctx: IngestContext,
    session: AsyncSession,
    transform_result: TransformStageResult,
    *,
    qdrant_router: QdrantRouter,
    postgres_router: PostgresRouter,
    ingest_plan: IngestGenerationPlan | None,
    rows_total: int,
    rows_ok: int,
    rows_skipped: int,
) -> int:
    chunks_written = 0
    qdrant_pending = list(transform_result.qdrant_records)
    allocated_chunk_ids: set[uuid.UUID] = set()

    if ingest_plan is not None:
        while qdrant_pending:
            batch = qdrant_pending[:QDRANT_FLUSH_SIZE]
            qdrant_pending = qdrant_pending[QDRANT_FLUSH_SIZE:]
            chunks_written += await qdrant_router.write(
                batch,
                ctx.doc_id,
                ctx.config_raw,
                ctx.document_context,
                session,
                ingest_generation=ingest_plan.staging,
                allocated_chunk_ids=allocated_chunk_ids,
            )
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.job_id == ctx.job_id)
                .values(
                    rows_total=rows_total,
                    rows_ok=rows_ok,
                    rows_skipped=rows_skipped,
                )
            )

    if transform_result.postgres_records:
        pg_context = dict(ctx.document_context)
        if ingest_plan is not None:
            pg_context["staging_generation"] = ingest_plan.staging
        await postgres_router.write(
            transform_result.postgres_records,
            ctx.doc_id,
            ctx.config_raw,
            pg_context,
            session,
        )

    return chunks_written


async def run_index_stage(
    ctx: IngestContext,
    session: AsyncSession,
    transform_result: TransformStageResult,
    *,
    qdrant_router: QdrantRouter,
    postgres_router: PostgresRouter,
    ingest_plan: IngestGenerationPlan | None,
    rows_total: int,
) -> IndexStageResult:
    result = IndexStageResult()
    result.chunks_written = await index_batch(
        ctx,
        session,
        transform_result,
        qdrant_router=qdrant_router,
        postgres_router=postgres_router,
        ingest_plan=ingest_plan,
        rows_total=rows_total,
        rows_ok=transform_result.rows_ok,
        rows_skipped=transform_result.rows_skipped,
    )

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="index",
        code="index_complete",
        detail={"chunks_written": result.chunks_written},
    )
    return result
