#!/usr/bin/env python3
"""Reconcile Qdrant vector counts with Postgres active ingest generations."""

from __future__ import annotations

import argparse
import asyncio
import sys

from spark.services.vector_reconcile_service import run_vector_reconcile


async def _main(*, factory_id: str | None, fix: bool) -> int:
    result = await run_vector_reconcile(factory_id=factory_id, auto_fix=fix)
    if result.mismatch_count:
        print(
            f"{result.mismatch_count} document(s) with Qdrant/PG generation drift "
            f"(fixed={result.fixed_count}, rate={result.drift_rate:.2%})"
        )
        return 1
    print("ingest vector mirror OK")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Delete stale Qdrant generations that do not match the active pointer",
    )
    parser.add_argument(
        "--factory-id",
        default=None,
        help="Limit reconcile to a single factory",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(factory_id=args.factory_id, fix=args.fix)))


if __name__ == "__main__":
    main()
