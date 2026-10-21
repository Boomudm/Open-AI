"""Chaos — staging abort leaves active generation unchanged (no orphan retrievable swap)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.index.saga import IngestGenerationPlan, abort_staging_ingest


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_staging_abort_does_not_promote_staging_generation() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=3, active=2, is_reingest=True)

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(return_value=None),
    ) as abort_mock:
        await abort_staging_ingest(
            doc_id=doc_id,
            plan=plan,
            qdrant_router=AsyncMock(),
            session=AsyncMock(),
            collection="spark_docs",
        )

    abort_mock.assert_awaited_once()
    assert plan.active == 2
    assert plan.staging == 3


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_staging_cleanup_failure_is_fail_closed() -> None:
    from spark.ingestion.errors import PermanentIngestError

    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(side_effect=RuntimeError("qdrant timeout")),
    ):
        with pytest.raises(PermanentIngestError) as exc_info:
            await abort_staging_ingest(
                doc_id=doc_id,
                plan=plan,
                qdrant_router=AsyncMock(),
                session=AsyncMock(),
                collection="spark_docs",
            )
    assert exc_info.value.reason_code == "staging_cleanup_failed"
