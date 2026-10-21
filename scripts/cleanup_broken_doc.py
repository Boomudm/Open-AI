#!/usr/bin/env python3
"""One-shot cleanup for a broken ingest document.

Deletes all DocumentChunk rows from Postgres and all Qdrant points for a
given doc_id, then resets the document status to 'pending' so it can be
re-ingested cleanly.

Usage:
    cd ~/spark
    source .venv/bin/activate
    PYTHONPATH=src python scripts/cleanup_broken_doc.py \
        --doc-id 8ab95584-8467-4163-be7f-ae208d01dd74

    # Dry-run (print what would be deleted, change nothing):
    PYTHONPATH=src python scripts/cleanup_broken_doc.py \
        --doc-id 8ab95584-8467-4163-be7f-ae208d01dd74 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import delete, select, update

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.core.qdrant import get_async_qdrant_client
from spark.core.config import settings
from spark.db.models.docs import Document, DocumentChunk

configure_logging()
log = get_logger("cleanup_broken_doc")


async def cleanup(doc_id: uuid.UUID, *, dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc is None:
            print(f"❌  Document {doc_id} not found in Postgres — nothing to clean.")
            return

        print(f"\n📄  Document: {doc.title or doc.doc_id}  (type={doc.document_type})")
        print(f"    ingest_status        = {doc.ingest_status}")
        print(f"    chunks_count         = {doc.chunks_count}")
        print(f"    active_generation    = {doc.active_ingest_generation}")

        # Count chunks
        chunk_rows = (
            await session.execute(
                select(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
            )
        ).scalars().all()

        qdrant_point_ids = [str(c.qdrant_point_id) for c in chunk_rows if c.qdrant_point_id]
        print(f"\n🗄️   Postgres chunks     = {len(chunk_rows)}")
        print(f"🔷  Qdrant point ids    = {len(qdrant_point_ids)}")

        if dry_run:
            print("\n🔵  DRY RUN — no changes made.  Re-run without --dry-run to apply.")
            return

        # Delete from Qdrant
        if qdrant_point_ids:
            qdrant = get_async_qdrant_client()
            collection = settings.qdrant_collection
            try:
                from qdrant_client.models import PointIdsList
                await qdrant.delete(
                    collection_name=collection,
                    points_selector=PointIdsList(points=qdrant_point_ids),
                )
                print(f"✅  Deleted {len(qdrant_point_ids)} points from Qdrant collection '{collection}'")
            except Exception as exc:
                print(f"⚠️   Qdrant delete failed (continuing): {exc}")

        # Delete from Postgres
        result = await session.execute(
            delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
        )
        deleted_rows = result.rowcount
        print(f"✅  Deleted {deleted_rows} rows from document_chunks")

        # Reset document status
        await session.execute(
            update(Document)
            .where(Document.doc_id == doc_id)
            .values(
                ingest_status="pending",
                chunks_count=0,
                active_ingest_generation=0,
                retrieval_enabled=False,
            )
        )
        await session.commit()
        print(f"✅  Reset document status → pending, chunks_count=0")
        print("\n🎯  Done. You can now re-upload or re-trigger ingest for this document.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up a broken ingest document")
    parser.add_argument("--doc-id", required=True, help="Document UUID to clean")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without making any changes",
    )
    args = parser.parse_args()
    doc_id = uuid.UUID(args.doc_id)
    asyncio.run(cleanup(doc_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
