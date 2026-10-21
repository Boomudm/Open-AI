#!/usr/bin/env python3
"""Backfill LLM topic tags for question_analytics (default 90 days)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging
from spark.services.topic_tagger_service import tag_batch

configure_logging()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill question topic tags via LLM")
    parser.add_argument("--factory-id", default=None)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        count = await tag_batch(
            session,
            factory_id=args.factory_id,
            lookback_days=args.days,
            limit=args.limit,
        )
    print(f"Tagged {count} question_analytics rows")


if __name__ == "__main__":
    asyncio.run(main())
