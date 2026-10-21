"""Lightweight re-validation gate for verified Q&A cache hits (Phase 12)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.core.metrics import qa_cache_invalidate_total
from spark.core.security import Principal
from spark.db.models.docs import Document, DocumentChunk
from spark.db.models.qa_cache import VerifiedQACache
from spark.services.qa_cache_service import QACacheService, qa_cache_service

log = get_logger(__name__)


async def _invalidate_entry(db: AsyncSession, cache_id: uuid.UUID, reason: str) -> None:
    await db.execute(delete(VerifiedQACache).where(VerifiedQACache.cache_id == cache_id))
    qa_cache_invalidate_total.inc()
    log.info("qa_cache_revalidation_failed", cache_id=str(cache_id), reason=reason)


async def _chunks_in_active_generation(
    db: AsyncSession,
    sources: list[dict[str, Any]],
) -> bool:
    chunk_ids: list[uuid.UUID] = []
    for src in sources:
        raw = src.get("chunk_id") if isinstance(src, dict) else None
        if not raw:
            continue
        try:
            chunk_ids.append(uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            return False
    if not chunk_ids:
        return True

    rows = (
        await db.execute(
            select(
                DocumentChunk.chunk_id,
                DocumentChunk.ingest_generation,
                Document.active_ingest_generation,
            )
            .join(Document, DocumentChunk.doc_id == Document.doc_id)
            .where(DocumentChunk.chunk_id.in_(chunk_ids))
        )
    ).all()
    if len(rows) != len(set(chunk_ids)):
        return False
    for row in rows:
        if int(row.ingest_generation) != int(row.active_ingest_generation):
            return False
    return True


async def revalidate_cache_hit(
    db: AsyncSession,
    *,
    cache_id: str,
    factory_id: str,
    sources: list[dict[str, Any]],
    source_doc_ids: list[uuid.UUID] | None,
    principal: Principal | None,
    allowed_doc_ids: list[str] | None,
    expected_fingerprint: str,
    stored_fingerprint: str | None,
    svc: QACacheService | None = None,
) -> bool:
    """Return True when a cache row is still safe to serve; invalidate row on failure."""
    service = svc or qa_cache_service
    cache_uuid = uuid.UUID(str(cache_id))

    if stored_fingerprint and stored_fingerprint != expected_fingerprint:
        await _invalidate_entry(db, cache_uuid, "fingerprint_mismatch")
        return False

    if principal and not principal.is_admin and factory_id not in principal.factory_access:
        await _invalidate_entry(db, cache_uuid, "rbac_factory_denied")
        return False

    doc_ids = list(source_doc_ids or [])
    if allowed_doc_ids is not None and doc_ids:
        allowed = {str(item) for item in allowed_doc_ids}
        for doc_id in doc_ids:
            if str(doc_id) not in allowed:
                await _invalidate_entry(db, cache_uuid, "rbac_doc_denied")
                return False

    if not await service._docs_still_valid(db, doc_ids):
        await _invalidate_entry(db, cache_uuid, "source_doc_invalid")
        return False

    if not await service._chunks_still_valid(db, list(sources or []), stored_fingerprint):
        await _invalidate_entry(db, cache_uuid, "chunk_snapshot_stale")
        return False

    if not await _chunks_in_active_generation(db, list(sources or [])):
        await _invalidate_entry(db, cache_uuid, "generation_stale")
        return False

    return True
