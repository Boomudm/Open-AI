"""Document-level ingest advisory lock tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.ingestion.lock import IngestDocLock


@pytest.mark.asyncio
async def test_acquire_returns_true_when_lock_free() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=True)
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    lock = IngestDocLock(session)
    assert await lock.acquire(doc_id, job_id) is True
    session.scalar.assert_awaited_once()
    await lock.release(doc_id, job_id)
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_acquire_returns_false_when_lock_held() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=False)
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    lock = IngestDocLock(session)
    assert await lock.acquire(doc_id, job_id) is False
    await lock.release(doc_id, job_id)
    session.scalar.assert_awaited_once()
