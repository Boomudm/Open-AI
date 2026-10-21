#!/usr/bin/env python3
"""Queue only documents created by seed_prototype.py for real RAG ingestion."""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.storage import get_storage
from spark.workers.tasks import ingest_document_task


async def queue_prototype_docs() -> int:
    queued = 0
    async with AsyncSessionLocal() as session:
        docs = (
            await session.execute(
                select(Document)
                .where(Document.factory_id == "F-01")
                .where(Document.extra_metadata["prototype_seed"].as_boolean() == True)  # noqa: E712
                .order_by(Document.source_file)
            )
        ).scalars().all()
        if len(docs) != 5:
            raise RuntimeError(f"Expected exactly 5 prototype documents, found {len(docs)}")

        storage = get_storage()
        for doc in docs:
            if not doc.storage_uri or not await storage.exists(doc.storage_uri):
                raise RuntimeError(f"Stored file missing for prototype document {doc.doc_id}")
            active = await session.scalar(
                select(IngestionJob).where(
                    IngestionJob.doc_id == doc.doc_id,
                    IngestionJob.status.in_(("queued", "running", "started")),
                ).limit(1)
            )
            if active:
                print(f"Already active: {doc.title} ({active.job_id})")
                continue

            job = IngestionJob(
                job_id=uuid.uuid4(), doc_id=doc.doc_id, factory_id=doc.factory_id,
                machine_id=doc.machine_id, document_type=doc.document_type,
                original_filename=doc.original_filename or doc.source_file,
                file_size_bytes=doc.file_size_bytes, status="queued",
            )
            session.add(job)
            await session.flush()
            doc.ingest_status = "pending"
            context = {
                "factory_id": doc.factory_id,
                "machine_id": doc.machine_id,
                "document_type": doc.document_type,
                "document_category": doc.document_category,
                "language": doc.language,
                "revision": doc.revision,
                "revision_sort_key": doc.revision_sort_key,
                "title": doc.title,
                "source_file": doc.source_file,
                "file_hash_sha256": doc.file_hash_sha256,
            }
            result = ingest_document_task.delay(
                doc_id=str(doc.doc_id), storage_uri=doc.storage_uri,
                document_type=doc.document_type, document_context=context,
                job_id=str(job.job_id),
            )
            job.celery_task_id = result.id
            queued += 1
            print(f"Queued: {doc.title} ({job.job_id})")
        await session.commit()
    return queued


if __name__ == "__main__":
    count = asyncio.run(queue_prototype_docs())
    print(f"Queued {count} prototype document(s)")
