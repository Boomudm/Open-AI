#!/usr/bin/env python3
"""Blue-green Qdrant collection migration for embedding model / dimension changes."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy import select

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.llm_profile import embedding_dimension
from spark.core.logging import get_logger
from spark.core.qdrant import ensure_collection, get_async_qdrant_client
from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.chunking.context_header import embed_text_with_header
from spark.ingestion.embedder import Embedder
from spark.ingestion.embed_lineage import embed_lineage_for_text

log = get_logger(__name__)


def target_collection_for_doc(doc: Document, suffix: str) -> str:
    base = settings.qdrant_collection
    strategy = settings.qdrant_shard_strategy
    if strategy == "single" or not doc.factory_id:
        return f"{base}__{suffix}"
    if strategy == "per_factory":
        return f"{base}__{doc.factory_id.lower()}__{suffix}"
    cat = (doc.document_category or "misc").lower()
    return f"{base}__{doc.factory_id.lower()}__{cat}__{suffix}"


async def _load_active_chunks(
    *,
    factory_id: str | None,
    limit: int | None,
) -> list[tuple[Document, DocumentChunk]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Document, DocumentChunk)
            .join(DocumentChunk, DocumentChunk.doc_id == Document.doc_id)
            .where(
                Document.chunks_count > 0,
                Document.ingest_status != "failed",
                DocumentChunk.ingest_generation == Document.active_ingest_generation,
            )
            .order_by(Document.doc_id, DocumentChunk.chunk_index)
        )
        if factory_id:
            stmt = stmt.where(Document.factory_id == factory_id)
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).all()
        return [(doc, chunk) for doc, chunk in rows]


async def _migrate(
    *,
    target_suffix: str,
    factory_id: str | None,
    dry_run: bool,
    limit: int | None,
) -> dict[str, Any]:
    suffix = target_suffix.strip()
    if not suffix:
        raise ValueError("target_suffix is required (e.g. v2)")

    pairs = await _load_active_chunks(factory_id=factory_id, limit=limit)
    collections: dict[str, int] = {}
    for doc, _chunk in pairs:
        name = target_collection_for_doc(doc, suffix)
        collections[name] = collections.get(name, 0) + 1

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "target_suffix": suffix,
        "factory_id": factory_id,
        "chunk_count": len(pairs),
        "collections": collections,
        "vector_size": embedding_dimension(),
    }
    if dry_run or not pairs:
        return summary

    embedder = Embedder.get()
    client = get_async_qdrant_client()
    vector_size = embedding_dimension()
    for collection in collections:
        ensure_collection(collection, vector_size=vector_size)

    batch_size = 32
    written = 0
    pending_by_collection: dict[str, list[PointStruct]] = {}

    for start in range(0, len(pairs), batch_size):
        batch = pairs[start : start + batch_size]
        texts: list[str] = []
        for doc, chunk in batch:
            document_context = {
                "factory_id": doc.factory_id,
                "machine_id": doc.machine_id,
                "document_type": doc.document_type,
                "document_category": doc.document_category,
                "language": doc.language,
                "source_file": doc.source_file,
                "title": doc.title,
            }
            payload = dict(chunk.payload or {})
            raw = (chunk.content or payload.get("page_content") or "").strip()
            texts.append(embed_text_with_header(raw, document_context, payload))
        vectors = await embedder.embed_documents(texts)

        for (doc, chunk), vector, embed_input in zip(batch, vectors, texts, strict=True):
            if len(vector) != vector_size:
                raise ValueError(
                    f"embedding dimension mismatch for chunk {chunk.chunk_id}: "
                    f"got {len(vector)}, expected {vector_size}"
                )
            collection = target_collection_for_doc(doc, suffix)
            payload = dict(chunk.payload or {})
            payload.update(
                embed_lineage_for_text(
                    embed_input,
                    profile=embedder.embed_profile(),
                    config_hash=str(payload.get("config_hash") or ""),
                )
            )
            point = PointStruct(id=str(chunk.chunk_id), vector=vector, payload=payload)
            pending_by_collection.setdefault(collection, []).append(point)
            written += 1

    for collection, points in pending_by_collection.items():
        for start in range(0, len(points), batch_size):
            await client.upsert(
                collection_name=collection,
                points=points[start : start + batch_size],
                wait=True,
            )

    summary["points_written"] = written
    summary["next_step"] = (
        f"Set QDRANT_COLLECTION_SUFFIX_VERSION={suffix} and restart API/workers "
        "after validating retrieval quality. Retain old collections until cutover is verified."
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-suffix", required=True, help="New collection suffix, e.g. v2")
    parser.add_argument("--factory-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Limit chunks (CI smoke)")
    args = parser.parse_args()

    try:
        summary = asyncio.run(
            _migrate(
                target_suffix=args.target_suffix,
                factory_id=args.factory_id,
                dry_run=args.dry_run,
                limit=args.limit,
            )
        )
    except Exception as exc:
        log.error("embedding_migration_failed", error=str(exc)[:300])
        raise SystemExit(1) from exc

    print(summary)


if __name__ == "__main__":
    main()
