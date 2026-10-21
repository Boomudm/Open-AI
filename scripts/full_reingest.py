#!/usr/bin/env python3
"""Queue full re-ingest for all documents in a factory."""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select, update

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.workers.tasks import ingest_document_task

configure_logging()
log = get_logger("full_reingest")


async def _queue_factory(*, factory_id: str, force: bool, storage_prefix: str | None) -> int:
    queued = 0
    async with AsyncSessionLocal() as session:
        stmt = select(Document).where(Document.factory_id == factory_id)
        if not force:
            stmt = stmt.where(Document.ingest_status != "failed")
        if storage_prefix:
            # Skip rows whose stored file is gone (e.g. test uploads that
            # pointed at pytest tmp paths) — queueing them only produces
            # guaranteed parser_failed jobs.
            stmt = stmt.where(Document.storage_uri.like(f"{storage_prefix}%"))
        docs = (await session.execute(stmt)).scalars().all()
        for doc in docs:
            job = IngestionJob(
                job_id=uuid.uuid4(),
                doc_id=doc.doc_id,
                factory_id=doc.factory_id,
                document_type=doc.document_type,
                original_filename=doc.original_filename or doc.source_file,
                status="queued",
            )
            session.add(job)
            await session.flush()

            context = {
                "factory_id": doc.factory_id,
                "machine_id": doc.machine_id,
                "document_type": doc.document_type,
                "document_category": doc.document_category,
                "language": doc.language,
                "revision": doc.revision,
                "title": doc.title,
                "source_file": doc.source_file,
            }
            await session.execute(
                update(Document)
                .where(Document.doc_id == doc.doc_id)
                .values(ingest_status="pending")
            )
            async_result = ingest_document_task.delay(
                doc_id=str(doc.doc_id),
                storage_uri=doc.storage_uri,
                document_type=doc.document_type,
                document_context=context,
                job_id=str(job.job_id),
            )
            job.celery_task_id = async_result.id
            queued += 1
            log.info(
                "full_reingest_queued",
                doc_id=str(doc.doc_id),
                job_id=str(job.job_id),
                factory_id=factory_id,
            )
        await session.commit()
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True, help="Factory id, e.g. f-01")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Include failed documents",
    )
    parser.add_argument(
        "--storage-prefix",
        default=None,
        help="Only queue documents whose storage_uri starts with this (e.g. s3://)",
    )
    args = parser.parse_args()
    count = asyncio.run(
        _queue_factory(
            factory_id=args.factory, force=args.force, storage_prefix=args.storage_prefix
        )
    )
    print(f"Queued {count} document(s) for factory {args.factory}")


if __name__ == "__main__":
    main()
