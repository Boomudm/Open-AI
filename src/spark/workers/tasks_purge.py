"""Celery tasks for compensating Qdrant generation purge."""

from __future__ import annotations

from spark.core.logging import get_logger
from spark.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    name="spark.workers.tasks_purge.dispatch_pending_purges",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    max_retries=5,
)
def dispatch_pending_purges_task(self) -> dict[str, int]:
    import asyncio

    from spark.core.database import AsyncSessionLocal
    from spark.ingestion.purge_outbox import process_pending_purges

    async def _run() -> dict[str, int]:
        async with AsyncSessionLocal() as session:
            result = await process_pending_purges(session)
            await session.commit()
            return result

    outcome = asyncio.run(_run())
    log.info("ingest_purge_batch_complete", **outcome)
    return outcome
