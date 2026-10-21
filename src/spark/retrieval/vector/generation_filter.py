"""Filter vector hits to the document's active ingest generation."""

from __future__ import annotations

from sqlalchemy import String, cast, select

from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document
from spark.retrieval.models import RetrievedDoc


async def filter_active_ingest_docs(docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """Drop stale Qdrant points from in-flight or superseded ingest generations."""
    doc_ids = {
        str(doc.payload.get("doc_id"))
        for doc in docs
        if doc.payload.get("doc_id")
    }
    if not doc_ids:
        return docs

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Document.doc_id, Document.active_ingest_generation).where(
                cast(Document.doc_id, String).in_(sorted(doc_ids))
            )
        )
        active_by_doc = {str(doc_id): int(generation or 1) for doc_id, generation in rows}

    kept: list[RetrievedDoc] = []
    for doc in docs:
        doc_id = str(doc.payload.get("doc_id") or "")
        if not doc_id:
            kept.append(doc)
            continue
        active = active_by_doc.get(doc_id, 1)
        point_generation = int(doc.payload.get("ingest_generation") or 1)
        if point_generation == active:
            kept.append(doc)
    return kept
