"""Scope filters for lexical queries (factory/machine/doc_type)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, cast, or_

from spark.db.models.docs import Document, DocumentChunk
from spark.retrieval.models import RAGFilter
from spark.retrieval.scoring import _coerce_uuid_strings


def scope_filters(
    rf: RAGFilter,
    allowed_doc_ids: list[str] | None,
) -> list[Any] | None:
    """Return scope WHERE clauses, or None when allowlist is empty (no results)."""
    where: list[Any] = [
        DocumentChunk.content.is_not(None),
        DocumentChunk.content != "",
        DocumentChunk.ingest_generation == Document.active_ingest_generation,
        Document.retrieval_enabled.is_(True),
    ]
    allowed = _coerce_uuid_strings(allowed_doc_ids)
    if allowed is not None:
        if not allowed:
            return None
        where.append(cast(Document.doc_id, String).in_(allowed))
    if rf.factory_id:
        where.append(Document.factory_id == rf.factory_id)
    if rf.machine_id:
        where.append(
            or_(Document.machine_id == rf.machine_id, Document.machine_id.is_(None))
        )
    if rf.document_category:
        where.append(Document.document_category == rf.document_category)
    if rf.document_type:
        where.append(Document.document_type == rf.document_type)
    if rf.language:
        where.append(Document.language == rf.language)
    if rf.only_active:
        today = datetime.now(tz=timezone.utc).date()
        where.append(or_(Document.expiry_date.is_(None), Document.expiry_date >= today))
    return where
