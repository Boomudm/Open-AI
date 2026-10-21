"""Bidirectional PG ↔ Qdrant staging verification."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.ingestion.index.drift_errors import IndexDriftError
from spark.ingestion.index.qdrant_writer import QdrantWriter

log = get_logger(__name__)

UNDER_COUNT_TOLERANCE = 0.05
GHOST_COUNT_TOLERANCE = 0.02

_SAFETY_DOC_TYPES = frozenset({"safety_procedure", "machine_manual", "sop"})


def _tolerances(doc_type: str | None) -> tuple[float, float]:
    if doc_type and doc_type in _SAFETY_DOC_TYPES:
        return 0.0, 0.0
    return UNDER_COUNT_TOLERANCE, GHOST_COUNT_TOLERANCE


async def verify_generation_counts(
    *,
    doc_id: uuid.UUID,
    generation: int,
    pg_count: int,
    qdrant_writer: QdrantWriter,
    collection: str | None,
    session: AsyncSession | None = None,
    payload_sample_rate: float = 0.01,
    document_type: str | None = None,
) -> None:
    """Bidirectional count check plus optional payload hash sampling."""
    if pg_count <= 0:
        return

    under_tol, ghost_tol = _tolerances(document_type)

    qdrant_count = await qdrant_writer.count_by_doc(
        doc_id,
        collection=collection,
        generation=generation,
    )

    if qdrant_count > pg_count:
        ghost_ratio = (qdrant_count - pg_count) / pg_count
        if ghost_ratio > ghost_tol:
            detail = (
                f"ghost points for doc {doc_id}: PG={pg_count} Qdrant={qdrant_count} "
                f"generation={generation} excess={ghost_ratio:.1%}"
            )
            log.error("ingest_swap_verify_ghost", doc_id=str(doc_id), detail=detail)
            raise IndexDriftError(detail)
    elif qdrant_count < pg_count:
        gap_ratio = (pg_count - qdrant_count) / pg_count
        if gap_ratio > under_tol:
            detail = (
                f"index drift for doc {doc_id}: PG={pg_count} Qdrant={qdrant_count} "
                f"generation={generation} gap={gap_ratio:.1%}"
            )
            log.error("ingest_swap_verify_failed", doc_id=str(doc_id), detail=detail)
            raise IndexDriftError(detail)

    if session is not None and payload_sample_rate > 0:
        from spark.ingestion.index.payload_audit import audit_payload_hash_sample

        await audit_payload_hash_sample(
            session,
            doc_id=doc_id,
            generation=generation,
            qdrant_writer=qdrant_writer,
            collection=collection,
            sample_rate=payload_sample_rate,
            document_type=document_type,
        )
