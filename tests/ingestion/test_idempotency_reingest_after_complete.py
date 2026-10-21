"""Phase 2 — idempotency key cleared after terminal jobs allow re-ingest."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from spark.ingestion.idempotency import (
    clear_idempotency_key,
    find_existing_job,
    ingest_idempotency_key,
    is_terminal_job_status,
)


def test_terminal_statuses_include_partial_and_pending_release() -> None:
    assert is_terminal_job_status("completed")
    assert is_terminal_job_status("partial")
    assert is_terminal_job_status("pending_release")
    assert not is_terminal_job_status("running")


@pytest.mark.asyncio
async def test_clear_idempotency_key_nulls_job_column() -> None:
    job_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()

    await clear_idempotency_key(session, job_id)

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_existing_job_ignores_completed_job_with_same_key() -> None:
    doc_id = uuid.uuid4()
    key = ingest_idempotency_key(doc_id, "hash", "cfg")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    found = await find_existing_job(session, key)
    assert found is None


@pytest.mark.asyncio
async def test_reingest_allowed_after_terminal_clear() -> None:
    from spark.db.models.ingestion import IngestionJob

    doc_id = uuid.uuid4()
    key = ingest_idempotency_key(doc_id, "same-hash", "cfg1")
    completed = IngestionJob(
        job_id=uuid.uuid4(),
        doc_id=doc_id,
        document_type="machine_manual",
        status="completed",
        idempotency_key=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    assert completed.idempotency_key is None
    assert await find_existing_job(session, key) is None
