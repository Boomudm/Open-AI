"""Celery tasks for scheduled PG ↔ Qdrant vector reconcile (Phase 5)."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.db.models.docs import Document
from spark.services.vector_reconcile_service import run_vector_reconcile
from spark.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="spark.workers.tasks_reconcile.reconcile_vectors_task")
def reconcile_vectors_task(
    factory_id: str | None = None,
    auto_fix: bool = False,
) -> dict[str, object]:
    result = asyncio.run(
        run_vector_reconcile(factory_id=factory_id, auto_fix=auto_fix)
    )
    log.info(
        "vector_reconcile_task_complete",
        factory_id=factory_id,
        auto_fix=auto_fix,
        mismatch_count=result.mismatch_count,
        fixed_count=result.fixed_count,
        reupserted_count=result.reupserted_count,
        drift_rate=round(result.drift_rate, 4),
    )
    payload = result.to_dict()
    if result.mismatch_count and not auto_fix:
        payload["status"] = "mismatches_remaining"
    elif result.mismatch_count:
        payload["status"] = "fixed" if (result.fixed_count or result.reupserted_count) else "mismatches_remaining"
    else:
        payload["status"] = "ok"
    return payload


@celery_app.task(name="spark.workers.tasks_reconcile.reconcile_all_factories_task")
def reconcile_all_factories_task(*, auto_fix: bool = True) -> dict[str, object]:
    """Reconcile every factory with indexed documents (15m cron)."""

    async def _run() -> dict[str, object]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(Document.factory_id)
                    .where(
                        Document.chunks_count > 0,
                        Document.factory_id.is_not(None),
                        Document.retrieval_enabled.is_(True),
                    )
                    .distinct()
                )
            ).scalars().all()
            factory_ids = sorted({str(r) for r in rows if r})

        summaries: list[dict[str, object]] = []
        total_mismatches = 0
        for fid in factory_ids:
            result = await run_vector_reconcile(factory_id=fid, auto_fix=auto_fix)
            total_mismatches += result.mismatch_count
            summaries.append({"factory_id": fid, "mismatch_count": result.mismatch_count})

        return {
            "status": "ok" if total_mismatches == 0 else "mismatches_remaining",
            "factories": len(factory_ids),
            "total_mismatches": total_mismatches,
            "summaries": summaries[:20],
        }

    # A single asyncio.run() for the whole task, not one per factory: each
    # asyncio.run() call closes its own event loop when it returns, but the
    # cached AsyncQdrantClient (module-level singleton) survives across those
    # calls — the second factory's reconcile then tried to reuse httpx
    # connections bound to the first call's already-closed loop, raising
    # "RuntimeError: Event loop is closed" (same root cause as the
    # cross-task version this file's sibling task_postrun hook already
    # fixes, just one level finer-grained: *within* one task, not between
    # tasks).
    return asyncio.run(_run())
