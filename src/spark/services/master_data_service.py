from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.docs import Document
from spark.db.models.feedback import KnowledgeFeedback
from spark.db.models.qa_cache import VerifiedQACache
from spark.db.models.org import (
    Component,
    Factory,
    Machine,
    MachineAlias,
)

_FACTORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,18}$")


class MasterDataService:
    def _machine_filters(
        self,
        *,
        factory_id: str | None,
        q: str | None,
        machine_type: str | None,
        allowed_factories: list[str] | None,
        include_inactive: bool = False,
    ):
        stmt = select(Machine)
        if not include_inactive:
            stmt = stmt.where(Machine.is_active == True)  # noqa: E712
        if factory_id:
            stmt = stmt.where(Machine.factory_id == factory_id)
        elif allowed_factories is not None:
            stmt = stmt.where(Machine.factory_id.in_(allowed_factories))
        if machine_type:
            stmt = stmt.where(Machine.machine_type == machine_type)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Machine.machine_name.ilike(like),
                    Machine.machine_id.ilike(like),
                    Machine.machine_type.ilike(like),
                )
            )
        return stmt

    async def count_machines(
        self,
        session: AsyncSession,
        factory_id: str | None = None,
        q: str | None = None,
        machine_type: str | None = None,
        allowed_factories: list[str] | None = None,
        include_inactive: bool = False,
    ) -> int:
        base = self._machine_filters(
            factory_id=factory_id,
            q=q,
            machine_type=machine_type,
            allowed_factories=allowed_factories,
            include_inactive=include_inactive,
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        return int((await session.execute(count_stmt)).scalar_one())

    async def list_machines(
        self,
        session: AsyncSession,
        factory_id: str | None = None,
        q: str | None = None,
        machine_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        allowed_factories: list[str] | None = None,
        include_inactive: bool = False,
    ) -> Sequence[Machine]:
        stmt = self._machine_filters(
            factory_id=factory_id,
            q=q,
            machine_type=machine_type,
            allowed_factories=allowed_factories,
            include_inactive=include_inactive,
        )
        stmt = stmt.order_by(Machine.factory_id, Machine.machine_id).limit(limit).offset(offset)
        return (await session.execute(stmt)).scalars().all()

    async def get_machine(self, session: AsyncSession, machine_id: str) -> Machine | None:
        return await session.get(Machine, machine_id)

    async def create_machine(self, session: AsyncSession, data: dict[str, Any]) -> Machine:
        existing = await session.get(Machine, data["machine_id"])
        if existing is not None:
            raise ValueError("machine_id already exists")
        machine = Machine(**data)
        session.add(machine)
        await session.commit()
        await session.refresh(machine)
        return machine

    async def add_machine_alias(
        self, session: AsyncSession, machine_id: str, alias: str, source: str = "manual"
    ) -> MachineAlias:
        ma = MachineAlias(machine_id=machine_id, alias=alias, source=source)
        session.add(ma)
        await session.commit()
        await session.refresh(ma)
        return ma

    async def list_factories(self, session: AsyncSession) -> Sequence[Factory]:
        return (await session.execute(select(Factory).order_by(Factory.factory_id))).scalars().all()

    async def create_factory(
        self,
        session: AsyncSession,
        *,
        factory_id: str,
        factory_name: str,
        location: str | None = None,
    ) -> Factory:
        normalized_id = factory_id.strip().upper()
        if not _FACTORY_ID_RE.match(normalized_id):
            raise ValueError("factory_id must be 2–19 chars (letters, numbers, -, _)")
        name = factory_name.strip()
        if not name:
            raise ValueError("factory_name is required")
        existing = await session.get(Factory, normalized_id)
        if existing is not None:
            raise ValueError("factory_id already exists")
        row = Factory(
            factory_id=normalized_id,
            factory_name=name,
            location=location.strip() if location else None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def delete_factory(self, session: AsyncSession, *, factory_id: str) -> None:
        normalized_id = factory_id.strip().upper()
        row = await session.get(Factory, normalized_id)
        if row is None:
            raise ValueError("factory not found")

        blockers: list[str] = []
        checks = (
            ("documents", select(func.count()).select_from(Document).where(Document.factory_id == normalized_id)),
            ("machines", select(func.count()).select_from(Machine).where(Machine.factory_id == normalized_id)),
            (
                "feedback",
                select(func.count())
                .select_from(KnowledgeFeedback)
                .where(KnowledgeFeedback.factory_id == normalized_id),
            ),
            (
                "qa cache entries",
                select(func.count())
                .select_from(VerifiedQACache)
                .where(VerifiedQACache.factory_id == normalized_id),
            ),
        )
        for label, stmt in checks:
            count = int((await session.execute(stmt)).scalar_one())
            if count > 0:
                blockers.append(f"{count} {label}")
        if blockers:
            raise ValueError(
                f"factory not empty ({', '.join(blockers)}) — remove dependent data first"
            )

        await session.delete(row)
        await session.commit()

    async def delete_machine(self, session: AsyncSession, *, machine_id: str) -> None:
        """Delete a machine, blocking while records depend on it.

        Owned children (aliases, components) are removed with the machine.
        Records that represent real history — documents, feedback, verified QA
        cache — block the delete so they are never silently orphaned.
        """
        row = await session.get(Machine, machine_id)
        if row is None:
            raise ValueError("machine not found")

        blockers: list[str] = []
        checks = (
            ("documents", select(func.count()).select_from(Document).where(Document.machine_id == machine_id)),
            (
                "feedback",
                select(func.count())
                .select_from(KnowledgeFeedback)
                .where(KnowledgeFeedback.machine_id == machine_id),
            ),
            (
                "qa cache entries",
                select(func.count())
                .select_from(VerifiedQACache)
                .where(VerifiedQACache.machine_id == machine_id),
            ),
        )
        for label, stmt in checks:
            count = int((await session.execute(stmt)).scalar_one())
            if count > 0:
                blockers.append(f"{count} {label}")
        if blockers:
            raise ValueError(
                f"machine not empty ({', '.join(blockers)}) — remove dependent data first"
            )

        await session.execute(delete(MachineAlias).where(MachineAlias.machine_id == machine_id))
        await session.execute(delete(Component).where(Component.machine_id == machine_id))
        await session.delete(row)
        await session.commit()
