"""Saga abort leaves live generation untouched."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.index.saga import IngestGenerationPlan, IngestIndexSaga


@pytest.mark.asyncio
async def test_abort_removes_staging_only() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    qdrant = AsyncMock()
    qdrant.delete_by_doc_generation = AsyncMock()

    session = AsyncMock()
    delete_result = MagicMock()
    delete_result.rowcount = 3
    session.execute = AsyncMock(return_value=delete_result)

    saga = IngestIndexSaga(doc_id=doc_id, plan=plan, qdrant_router=qdrant, collection="spark_docs")
    await saga.abort(session)

    qdrant.delete_by_doc_generation.assert_awaited_once_with(
        doc_id,
        generation=2,
        collection="spark_docs",
    )
    assert session.execute.await_count == 2
