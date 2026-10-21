#!/usr/bin/env python3
"""Rollback helper — pin documents to a prior active_ingest_generation (Phase 16).

Dry-run by default. Use --yes to emit SQL for operator review/execution.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from spark.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("rollback_generation_pin")


async def _list_docs(factory_id: str) -> list[tuple[UUID, int, str | None]]:
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    Document.doc_id,
                    Document.active_ingest_generation,
                    Document.document_type,
                ).where(
                    Document.factory_id == factory_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).all()
    return [(row.doc_id, int(row.active_ingest_generation or 1), row.document_type) for row in rows]


async def _apply_pin(
    *,
    factory_id: str,
    target_generation: int,
    dry_run: bool,
) -> int:
    docs = await _list_docs(factory_id)
    if not docs:
        print(f"No documents for factory {factory_id}")
        return 0

    changed = 0
    for doc_id, active_gen, doc_type in docs:
        if active_gen <= target_generation:
            continue
        changed += 1
        sql = (
            f"UPDATE documents SET active_ingest_generation = {target_generation} "
            f"WHERE doc_id = '{doc_id}';"
        )
        print(f"-- {doc_type or 'unknown'} gen {active_gen} -> {target_generation}")
        print(sql)
        if not dry_run:
            from sqlalchemy import update

            from spark.core.database import AsyncSessionLocal
            from spark.db.models.docs import Document

            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Document)
                    .where(Document.doc_id == doc_id)
                    .values(active_ingest_generation=target_generation)
                )
                await session.commit()

    log.info(
        "rollback_generation_pin",
        factory_id=factory_id,
        target_generation=target_generation,
        documents_changed=changed,
        dry_run=dry_run,
    )
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-id", required=True)
    parser.add_argument(
        "--target-generation",
        type=int,
        required=True,
        help="Revert active_ingest_generation to this value (must be < current)",
    )
    parser.add_argument("--yes", action="store_true", help="Apply updates (default: SQL dry-run only)")
    args = parser.parse_args()

    if args.target_generation < 1:
        print("target-generation must be >= 1", file=sys.stderr)
        return 1

    changed = asyncio.run(
        _apply_pin(
            factory_id=args.factory_id,
            target_generation=args.target_generation,
            dry_run=not args.yes,
        )
    )
    mode = "applied" if args.yes else "dry-run"
    print(f"rollback_generation_pin {mode}: {changed} document(s) affected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
