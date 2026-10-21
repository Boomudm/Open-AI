#!/usr/bin/env python3
"""Full re-ingest after Phase 5 sparse encoder change.

Hash-bucket sparse vectors (hash_sparse_legacy) are incompatible with BGE-M3
tokenizer sparse. Run after deploying Phase 5 and recreating Qdrant collections:

  uv run python scripts/qdrant_recreate_collections.py --yes
  uv run python scripts/full_reingest_v2_sparse.py --factory-id f-01 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from spark.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("full_reingest_v2_sparse")


ACTIVE_JOB_STATUSES = ("queued", "running", "started")


async def _reingest_factory(factory_id: str, *, dry_run: bool, storage_prefix: str | None) -> int:
    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document
    from spark.db.models.ingestion import IngestionJob
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = select(Document).where(
            Document.factory_id == factory_id,
            Document.storage_uri.isnot(None),
        )
        if storage_prefix:
            stmt = stmt.where(Document.storage_uri.like(f"{storage_prefix}%"))
        docs = (await session.execute(stmt)).scalars().all()

        candidates: list[Document] = []
        for doc in docs:
            active = await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.doc_id == doc.doc_id,
                    IngestionJob.status.in_(ACTIVE_JOB_STATUSES),
                )
                .limit(1)
            )
            if active:
                log.info(
                    "reingest_skip_active_job",
                    factory_id=factory_id,
                    doc_id=str(doc.doc_id),
                    job_id=str(active.job_id),
                    status=active.status,
                )
                continue
            candidates.append(doc)

        log.info("reingest_candidates", factory_id=factory_id, documents=len(candidates))
        if dry_run:
            return len(candidates)

        from spark.workers.tasks import ingest_document_task

        queued = 0
        for doc in candidates:
            doc.ingest_status = "pending"
            job = IngestionJob(
                job_id=uuid.uuid4(),
                doc_id=doc.doc_id,
                document_type=doc.document_type,
                original_filename=doc.original_filename or doc.source_file,
                file_size_bytes=doc.file_size_bytes,
                factory_id=doc.factory_id,
                machine_id=doc.machine_id,
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
                "revision_sort_key": doc.revision_sort_key,
                "title": doc.title,
                "source_file": doc.source_file,
                "file_hash_sha256": doc.file_hash_sha256,
            }
            result = ingest_document_task.delay(
                doc_id=str(doc.doc_id),
                storage_uri=doc.storage_uri,
                document_type=doc.document_type,
                document_context=context,
                job_id=str(job.job_id),
            )
            job.celery_task_id = result.id
            queued += 1
            log.info(
                "full_reingest_v2_sparse_queued",
                factory_id=factory_id,
                doc_id=str(doc.doc_id),
                job_id=str(job.job_id),
            )
        await session.commit()
        return queued


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-id", action="append", required=True)
    parser.add_argument("--yes", action="store_true", help="Confirm destructive re-ingest queue")
    parser.add_argument("--dry-run", action="store_true", help="Count documents only")
    parser.add_argument(
        "--storage-prefix",
        default="s3://",
        help="Only queue documents whose storage_uri starts with this; set empty to disable",
    )
    args = parser.parse_args()

    if not args.yes and not args.dry_run:
        raise SystemExit("Refusing to run without --yes or --dry-run")

    storage_prefix = args.storage_prefix or None

    async def _run_all() -> int:
        try:
            total = 0
            for factory_id in args.factory_id:
                total += await _reingest_factory(
                    factory_id=factory_id,
                    dry_run=args.dry_run,
                    storage_prefix=storage_prefix,
                )
            return total
        finally:
            from spark.core.database import engine

            await engine.dispose()

    total = asyncio.run(_run_all())
    action = "would queue" if args.dry_run else "queued"
    print(f"{action} {total} document(s) for full re-ingest (sparse_encoder v2)")


if __name__ == "__main__":
    main()
