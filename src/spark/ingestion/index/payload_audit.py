"""Sample PG ↔ Qdrant payload hash and key compliance audit for staging verification."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.contracts.rag_payload_contract import (
    QDRANT_PAYLOAD_FIELDS,
    safety_document_types_for_audit,
)
from spark.core.logging import get_logger
from spark.core.qdrant import get_async_qdrant_client
from spark.db.models.docs import DocumentChunk
from spark.ingestion.index.drift_errors import IndexDriftError
from spark.ingestion.index.qdrant_writer import QdrantWriter

log = get_logger(__name__)

DEFAULT_SAMPLE_RATE = 0.01
MIN_SAMPLE_SIZE = 1
MAX_SAMPLE_SIZE = 50
SAFETY_MAX_SAMPLE_SIZE = 10_000


def _effective_sample_size(*, total: int, document_type: str | None, sample_rate: float) -> int:
    safety_types = safety_document_types_for_audit()
    if document_type in safety_types:
        return min(total, SAFETY_MAX_SAMPLE_SIZE)
    return min(MAX_SAMPLE_SIZE, max(MIN_SAMPLE_SIZE, int(total * sample_rate)))


def _audit_payload_keys(payload: dict, *, chunk_id: str) -> list[str]:
    unknown = set(payload.keys()) - QDRANT_PAYLOAD_FIELDS
    if not unknown:
        return []
    return [f"unknown payload keys {sorted(unknown)} chunk={chunk_id}"]


async def audit_payload_hash_sample(
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    generation: int,
    qdrant_writer: QdrantWriter,
    collection: str | None,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    document_type: str | None = None,
) -> None:
    """Compare content_hash, embed lineage, and payload key contract for PG sample."""
    del qdrant_writer
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.doc_id == doc_id,
                DocumentChunk.ingest_generation == generation,
            )
        )
        or 0
    )
    if total <= 0:
        return

    sample_size = _effective_sample_size(
        total=total,
        document_type=document_type,
        sample_rate=sample_rate,
    )
    base_query = select(
        DocumentChunk.qdrant_point_id,
        DocumentChunk.content_hash,
        DocumentChunk.embed_model_version,
    ).where(
        DocumentChunk.doc_id == doc_id,
        DocumentChunk.ingest_generation == generation,
    )
    if document_type in safety_document_types_for_audit():
        rows = (await session.execute(base_query)).all()
    else:
        rows = (
            await session.execute(
                base_query.order_by(func.random()).limit(sample_size)
            )
        ).all()

    if not rows:
        return

    from spark.core.config import settings

    coll_name = collection or settings.qdrant_collection
    point_ids = [str(row.qdrant_point_id) for row in rows]
    client = get_async_qdrant_client()
    retrieved = await client.retrieve(collection_name=coll_name, ids=point_ids, with_payload=True)
    by_id = {str(point.id): point for point in retrieved}

    mismatches: list[str] = []
    for row in rows:
        point = by_id.get(str(row.qdrant_point_id))
        if point is None:
            mismatches.append(f"missing point {row.qdrant_point_id}")
            continue
        payload = point.payload or {}
        q_hash = str(payload.get("content_hash") or "")
        pg_hash = str(row.content_hash or "")
        if pg_hash and q_hash and pg_hash != q_hash:
            mismatches.append(f"content_hash mismatch chunk={row.qdrant_point_id}")
        q_version = str(payload.get("embed_model_version") or payload.get("embed_model_id") or "")
        pg_version = str(row.embed_model_version or "")
        if pg_version and q_version and pg_version != q_version:
            mismatches.append(f"embed_model_version mismatch chunk={row.qdrant_point_id}")
        mismatches.extend(_audit_payload_keys(payload, chunk_id=str(row.qdrant_point_id)))

    if mismatches:
        detail = (
            f"payload audit failed for doc {doc_id} generation={generation}: "
            + "; ".join(mismatches[:5])
        )
        log.error("ingest_payload_audit_failed", doc_id=str(doc_id), detail=detail)
        raise IndexDriftError(detail)

    log.info(
        "ingest_payload_audit_ok",
        doc_id=str(doc_id),
        generation=generation,
        sampled=len(rows),
        total=total,
        document_type=document_type,
        full_audit=document_type in safety_document_types_for_audit(),
    )
