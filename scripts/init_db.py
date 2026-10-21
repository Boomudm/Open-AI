#!/usr/bin/env python3
"""Create tables (idempotent) and seed default roles.

Usage:
  python scripts/init_db.py

This is a convenience script. For production prefer:
  alembic upgrade head
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select, text

from spark.core.database import AsyncSessionLocal, Base, engine
from spark.core.logging import configure_logging, get_logger
from spark.db.models.org import Role

configure_logging()
log = get_logger("init_db")

DEFAULT_ROLES = [
    ("admin", "Full access to all resources"),
    ("employee", "Floor worker — chat and document upload"),
    ("operator", "Supervisor / operator — dashboard and insights"),
]


async def create_tables() -> None:
    log.info("init_db_start")
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
        await conn.run_sync(Base.metadata.create_all)
    log.info("init_db_tables_created")


async def seed_roles() -> None:
    async with AsyncSessionLocal() as session:
        for code, desc in DEFAULT_ROLES:
            exists = await session.scalar(select(Role).where(Role.role_code == code))
            if not exists:
                session.add(Role(role_code=code, description=desc))
        await session.commit()
    log.info("init_db_roles_seeded")


async def main() -> None:
    await create_tables()
    await seed_roles()
    log.info("init_db_complete")


if __name__ == "__main__":
    asyncio.run(main())
