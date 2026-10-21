"""Atomic version-swap ingest: stage a new generation, flip pointer, delete the old."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.index.qdrant_writer import QdrantWriter
from spark.ingestion.index.saga import (
    IngestGenerationPlan,
    IngestIndexSaga,
    IngestSagaState,
    abort_staging_ingest,
    commit_ingest_swap,
)
from spark.ingestion.purge_outbox import enqueue_purge

__all__ = [
    "IngestGenerationPlan",
    "IngestIndexSaga",
    "IngestSagaState",
    "abort_staging_ingest",
    "commit_ingest_swap",
    "purge_superseded_qdrant_generations",
    "resolve_ingest_generation",
]


async def resolve_ingest_generation(
    session: AsyncSession,
    doc_id: uuid.UUID,
) -> IngestGenerationPlan:
    """Choose the staging generation without deleting the live index."""
    doc = await session.get(Document, doc_id)
    active = int(doc.active_ingest_generation if doc else 1) or 1
    chunk_count = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.doc_id == doc_id)
    )
    has_live_index = bool(chunk_count) or bool(doc and doc.chunks_count > 0)
    if not has_live_index:
        return IngestGenerationPlan(staging=1, active=0, is_reingest=False)
    return IngestGenerationPlan(staging=active + 1, active=active, is_reingest=True)


async def purge_superseded_qdrant_generations(
    *,
    doc_id: uuid.UUID,
    plan: IngestGenerationPlan,
    qdrant_router: QdrantWriter,
    collection: str | None,
    session: AsyncSession,
) -> None:
    """Enqueue async purge — do not delete inline without outbox retry."""
    if not plan.is_reingest:
        return
    await enqueue_purge(
        session,
        doc_id=doc_id,
        keep_generation=plan.staging,
        collection=collection,
    )
