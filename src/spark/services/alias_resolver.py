from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.cache import Cache, cache_key
from spark.core.logging import get_logger
from spark.db.models.org import (
    Machine,
    MachineAlias,
)

log = get_logger(__name__)

CACHE_TTL_SECONDS = 600


def _norm(value: str) -> str:
    return value.strip().lower()


class AliasResolver:
    """Resolve free-form text labels to canonical machine_id.

    Lookup order:
      1. exact match in machines PK
      2. case-insensitive alias match
      3. trigram similarity ≥ 0.6 (Postgres pg_trgm)

    Results are cached in Redis (TTL 10min) keyed by normalized label.
    """

    def __init__(self) -> None:
        self._cache = Cache.get()

    async def resolve_machine(self, label: str, session: AsyncSession) -> str | None:
        if not label:
            return None
        norm = _norm(label)

        ck = cache_key("alias", "machine", norm)
        cached = await self._cache.get_json(ck)
        if cached is not None:
            return cached or None

        result = await session.execute(
            select(Machine.machine_id).where(func.lower(Machine.machine_id) == norm)
        )
        row = result.scalar_one_or_none()
        if row:
            await self._cache.set_json(ck, row, ttl=CACHE_TTL_SECONDS)
            return row

        result = await session.execute(
            select(MachineAlias.machine_id)
            .where(func.lower(MachineAlias.alias) == norm)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            await self._cache.set_json(ck, row, ttl=CACHE_TTL_SECONDS)
            return row

        try:
            result = await session.execute(
                select(
                    MachineAlias.machine_id,
                    func.similarity(MachineAlias.alias, label).label("sim"),
                )
                .order_by(func.similarity(MachineAlias.alias, label).desc())
                .limit(1)
            )
            best = result.first()
            if best and best.sim >= 0.6:
                await self._cache.set_json(ck, best.machine_id, ttl=CACHE_TTL_SECONDS)
                return best.machine_id
        except Exception as exc:
            log.debug("alias_trgm_unavailable", error=str(exc))

        await self._cache.set_json(ck, "", ttl=60)
        return None

