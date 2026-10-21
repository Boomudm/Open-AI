"""Ingest job idempotency key tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.db.models.ingestion import IngestionJob
from spark.ingestion.idempotency import find_existing_job, ingest_idempotency_key


def test_idempotency_key_is_stable() -> None:
    doc_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    key_a = ingest_idempotency_key(doc_id, "hash1", "cfg1")
    key_b = ingest_idempotency_key(doc_id, "hash1", "cfg1")
    key_c = ingest_idempotency_key(doc_id, "hash2", "cfg1")
    assert key_a == key_b
    assert key_a != key_c
    assert str(doc_id) in key_a


@pytest.mark.asyncio
async def test_find_existing_job_returns_active_match() -> None:
    doc_id = uuid.uuid4()
    key = ingest_idempotency_key(doc_id, "deadbeef", "cfgdead")
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

    found = await find_existing_job(session, key)
    assert found is job
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_existing_job_returns_none_when_missing() -> None:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    found = await find_existing_job(session, "missing-key")
    assert found is None


@pytest.mark.asyncio
async def test_ingest_endpoint_returns_existing_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.api.v1.endpoints import ingest as ingest_module

    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    existing = MagicMock(spec=IngestionJob)
    existing.job_id = job_id
    existing.status = "running"
    existing.celery_task_id = "celery-1"

    monkeypatch.setattr(ingest_module, "find_existing_job", AsyncMock(return_value=existing))
    monkeypatch.setattr(
        ingest_module,
        "resolve_ingest_config",
        MagicMock(return_value=MagicMock(config_hash=MagicMock(return_value="cfg1"))),
    )

    key = ingest_idempotency_key(doc_id, "hash", "cfg1")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=existing)

    found = await ingest_module.find_existing_job(session, key)
    assert found.job_id == job_id
    assert found.status == "running"
