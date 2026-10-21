"""Postgres advisory lock for at-most-one active ingest per document."""

from __future__ import annotations

import uuid
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger

log = get_logger(__name__)

_ADVISORY_LOCK_SQL = "SELECT pg_try_advisory_lock(hashtextextended(:doc_id, 0))"
_ADVISORY_UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtextextended(:doc_id, 0))"


class IngestDocLock:
    """Session-scoped Postgres advisory lock keyed by doc_id (64-bit hash)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._held: dict[uuid.UUID, uuid.UUID] = {}

    async def __aenter__(self) -> IngestDocLock:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for doc_id, job_id in list(self._held.items()):
            await self.release(doc_id, job_id)

    async def acquire(
        self,
        doc_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        ttl_sec: int = 7200,
    ) -> bool:
        del ttl_sec  # session lock; released explicitly or on disconnect
        result = await self._session.scalar(
            text(_ADVISORY_LOCK_SQL),
            {"doc_id": str(doc_id)},
        )
        acquired = bool(result)
        if acquired:
            self._held[doc_id] = job_id
            log.debug("ingest_doc_lock_acquired", doc_id=str(doc_id), job_id=str(job_id))
        else:
            log.info("ingest_doc_lock_busy", doc_id=str(doc_id), job_id=str(job_id))
        return acquired

    async def release(self, doc_id: uuid.UUID, job_id: uuid.UUID) -> None:
        if doc_id not in self._held:
            return
        await self._session.scalar(
            text(_ADVISORY_UNLOCK_SQL),
            {"doc_id": str(doc_id)},
        )
        self._held.pop(doc_id, None)
        log.debug("ingest_doc_lock_released", doc_id=str(doc_id), job_id=str(job_id))

    async def heartbeat(self, doc_id: uuid.UUID, job_id: uuid.UUID) -> None:
        del doc_id, job_id
        # Session advisory locks do not require heartbeat; reserved for Redis lease option.
