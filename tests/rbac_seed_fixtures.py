"""Shared factory seed data for RBAC integration tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from spark.core.database import AsyncSessionLocal
from spark.db.models.org import Factory, Machine


@dataclass(frozen=True)
class RbacSeed:
    factory_f01: str = "RBAC-F01"
    factory_f02: str = "RBAC-F02"
    machine_f01: str = "MC-RBAC-01"


SEED = RbacSeed()

DEMO_FACTORIES: tuple[tuple[str, str], ...] = (
    ("F-01", "Factory 01"),
    ("F-02", "Factory 02"),
)


async def ensure_demo_factories() -> None:
    """Ensure canonical demo factory rows exist (CI starts with an empty DB)."""
    async with AsyncSessionLocal() as session:
        for fid, name in DEMO_FACTORIES:
            if await session.get(Factory, fid) is None:
                session.add(Factory(factory_id=fid, factory_name=name))
        await session.commit()


async def ensure_rbac_seed() -> None:
    async with AsyncSessionLocal() as session:
        for fid, name in (
            (SEED.factory_f01, "RBAC Factory 01"),
            (SEED.factory_f02, "RBAC Factory 02"),
        ):
            if await session.get(Factory, fid) is None:
                session.add(Factory(factory_id=fid, factory_name=name))
        if await session.get(Machine, SEED.machine_f01) is None:
            session.add(
                Machine(
                    machine_id=SEED.machine_f01,
                    factory_id=SEED.factory_f01,
                    machine_name="RBAC Machine 01",
                )
            )
        await session.commit()


def run_rbac_seed() -> None:
    asyncio.run(ensure_rbac_seed())
