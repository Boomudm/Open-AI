"""Upload-level document dedup by file hash (shared by HTTP and batch CLI)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.db.models.docs import Document

log = get_logger(__name__)


async def find_document_by_upload_hash(
    session: AsyncSession,
    *,
    factory_id: str,
    file_hash: str,
    machine_id: str | None,
) -> Document | None:
    """Lookup existing document by (factory_id, machine_id?, file_hash_sha256).

    Dedup is always scoped to the target ``factory_id``. A file that hashes the
    same as a document in a *different* factory must NOT match here — otherwise a
    re-ingest would relocate another tenant's document across the factory
    boundary (a data-isolation break). Within the factory we first try the exact
    machine, then fall back to any machine in the same factory.
    """
    in_factory = select(Document).where(
        Document.file_hash_sha256 == file_hash,
        Document.factory_id == factory_id,
    )
    if machine_id:
        exact = await session.scalar(in_factory.where(Document.machine_id == machine_id))
    else:
        exact = await session.scalar(in_factory.where(Document.machine_id.is_(None)))
    if exact:
        return exact
    # Same-factory fallback (any machine) — never cross-factory. Uniqueness is
    # scoped to (factory_id, file_hash_sha256), so the same file can exist as an
    # independent document in another factory.
    return await session.scalar(in_factory)


async def mark_document_reingest_pending(
    session: AsyncSession,
    doc: Document,
    *,
    factory_id: str,
    machine_id: str | None,
    document_type: str,
    document_category: str | None,
) -> Document:
    """Requeue ingest on the same doc_id for generation-swap re-ingest."""
    doc.ingest_status = "pending"
    doc.factory_id = factory_id
    doc.machine_id = machine_id
    doc.document_type = document_type
    if document_category:
        doc.document_category = document_category
    log.info("ingest_duplicate_requeue", doc_id=str(doc.doc_id), file_hash=(doc.file_hash_sha256 or "")[:12])
    return doc


async def resolve_or_create_doc_id(
    session: AsyncSession,
    *,
    factory_id: str,
    file_hash: str,
    machine_id: str | None,
    document_type: str,
    document_category: str | None,
) -> tuple[uuid.UUID, Document | None, bool]:
    """Return (doc_id, existing_doc_or_none, is_reingest)."""
    existing = await find_document_by_upload_hash(
        session,
        factory_id=factory_id,
        file_hash=file_hash,
        machine_id=machine_id,
    )
    if existing:
        await mark_document_reingest_pending(
            session,
            existing,
            factory_id=factory_id,
            machine_id=machine_id,
            document_type=document_type,
            document_category=document_category,
        )
        return existing.doc_id, existing, True
    return uuid.uuid4(), None, False
