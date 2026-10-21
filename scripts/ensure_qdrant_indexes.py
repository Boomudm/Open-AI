#!/usr/bin/env python3
"""Create Qdrant collection(s) + payload indexes (idempotent)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.core.qdrant import ensure_collection
from spark.core.qdrant_strategy import list_search_collections
from spark.db.models.org import Factory

configure_logging()
log = get_logger("ensure_qdrant_indexes")


async def _factory_ids() -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = list(
            (await session.execute(select(Factory.factory_id).order_by(Factory.factory_id))).scalars().all()
        )
    return rows or ["F-01", "F-02"]


def main() -> None:
    log.info("qdrant_setup_start")
    factory_ids = asyncio.run(_factory_ids())
    for coll in list_search_collections(None, factory_ids=factory_ids):
        ensure_collection(coll)
        log.info("qdrant_collection_ready", collection=coll)
    log.info("qdrant_setup_complete", factories=factory_ids)


if __name__ == "__main__":
    main()
