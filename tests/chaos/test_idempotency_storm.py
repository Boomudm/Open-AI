"""Chaos — duplicate enqueue storm returns single in-flight job."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from spark.ingestion.idempotency import find_existing_job, ingest_idempotency_key
from spark.db.models.ingestion import IngestionJob


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_idempotency_storm_returns_same_job_id() -> None:
    doc_id = uuid.uuid4()
    key = ingest_idempotency_key(doc_id, "same-hash", "cfg-v1")
    job = IngestionJob(
        job_id=uuid.uuid4(),
        doc_id=doc_id,
        document_type="machine_manual",
        status="running",
        idempotency_key=key,
        created_at=datetime.now(tz=timezone.utc),
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=job)

    results = await asyncio.gather(*[find_existing_job(session, key) for _ in range(100)])
    assert all(result is job for result in results)
    assert session.scalar.await_count == 100


@pytest.mark.chaos
def test_idempotency_key_stable_under_storm() -> None:
    doc_id = uuid.uuid4()
    keys = {
        ingest_idempotency_key(doc_id, "hash-a", "cfg")
        for _ in range(1000)
    }
    assert len(keys) == 1
