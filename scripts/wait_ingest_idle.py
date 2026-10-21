#!/usr/bin/env python3
"""Poll ingestion_jobs until no queued/running jobs remain."""

from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import func, select

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.db.models.ingestion import IngestionJob

configure_logging()
log = get_logger("wait_ingest_idle")

ACTIVE_STATUSES = ("queued", "running")


async def _active_count() -> int:
    async with AsyncSessionLocal() as session:
        stmt = select(func.count()).select_from(IngestionJob).where(
            IngestionJob.status.in_(ACTIVE_STATUSES)
        )
        return int((await session.execute(stmt)).scalar_one())


async def wait_idle(*, timeout_sec: int, poll_sec: float) -> int:
    deadline = time.monotonic() + timeout_sec
    while True:
        active = await _active_count()
        if active == 0:
            log.info("ingest_idle", active_jobs=0)
            return 0
        if time.monotonic() >= deadline:
            log.error("ingest_idle_timeout", active_jobs=active, timeout_sec=timeout_sec)
            return 1
        log.info("ingest_jobs_pending", active_jobs=active)
        await asyncio.sleep(poll_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait until ingestion job queue is idle")
    parser.add_argument("--timeout", type=int, default=3600, help="Max wait seconds")
    parser.add_argument("--poll", type=float, default=10.0, help="Poll interval seconds")
    args = parser.parse_args()
    return asyncio.run(wait_idle(timeout_sec=args.timeout, poll_sec=args.poll))


if __name__ == "__main__":
    raise SystemExit(main())
