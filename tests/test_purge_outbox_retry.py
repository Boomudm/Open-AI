"""Purge outbox retry behavior."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from spark.db.models.ingestion import IngestPurgeOutbox
from spark.ingestion.purge_outbox import process_purge_row


@pytest.mark.asyncio
async def test_process_purge_row_retries_on_failure() -> None:
    row = IngestPurgeOutbox(
        purge_id=uuid.uuid4(),
        doc_id=uuid.uuid4(),
        keep_generation=2,
        collection="spark_docs",
        status="pending",
        attempt_count=0,
        next_retry_at=datetime.now(tz=timezone.utc),
    )
    router = AsyncMock()
    router.delete_by_doc_except_generation = AsyncMock(side_effect=RuntimeError("qdrant down"))

    session = AsyncMock()
    session.execute = AsyncMock()

    ok = await process_purge_row(session, row, qdrant_router=router)

    assert ok is False
    assert session.execute.await_count == 1
    update_call = session.execute.await_args.args[0]
    assert "ingest_purge_outbox" in str(update_call).lower()


@pytest.mark.asyncio
async def test_process_purge_row_marks_complete() -> None:
    row = IngestPurgeOutbox(
        purge_id=uuid.uuid4(),
        doc_id=uuid.uuid4(),
        keep_generation=2,
        collection="spark_docs",
        status="pending",
        attempt_count=0,
        next_retry_at=datetime.now(tz=timezone.utc),
    )
    router = AsyncMock()
    router.delete_by_doc_except_generation = AsyncMock()

    session = AsyncMock()
    session.execute = AsyncMock()

    ok = await process_purge_row(session, row, qdrant_router=router)

    assert ok is True
    # Purge sweeps the row's own collection plus every known base collection —
    # superseded generations may sit in a collection the row doesn't remember.
    from spark.core.qdrant_strategy import known_collections

    expected_collections = {"spark_docs"} | known_collections()
    purged_collections = {
        call.kwargs["collection"]
        for call in router.delete_by_doc_except_generation.await_args_list
    }
    assert purged_collections == expected_collections
