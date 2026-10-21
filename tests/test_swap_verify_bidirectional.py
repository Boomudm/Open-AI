"""Bidirectional swap verification tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.ingestion.index.swap_verify import IndexDriftError, verify_generation_counts


@pytest.mark.asyncio
async def test_verify_fails_when_qdrant_under_count_beyond_tolerance() -> None:
    writer = AsyncMock()
    writer.count_by_doc = AsyncMock(return_value=90)
    doc_id = uuid.uuid4()

    with pytest.raises(IndexDriftError, match="index drift"):
        await verify_generation_counts(
            doc_id=doc_id,
            generation=2,
            pg_count=100,
            qdrant_writer=writer,
            collection="spark_docs",
            session=None,
            payload_sample_rate=0.0,
        )


@pytest.mark.asyncio
async def test_verify_fails_on_ghost_points() -> None:
    writer = AsyncMock()
    writer.count_by_doc = AsyncMock(return_value=105)
    doc_id = uuid.uuid4()

    with pytest.raises(IndexDriftError, match="ghost points"):
        await verify_generation_counts(
            doc_id=doc_id,
            generation=2,
            pg_count=100,
            qdrant_writer=writer,
            collection="spark_docs",
            session=None,
            payload_sample_rate=0.0,
        )


@pytest.mark.asyncio
async def test_verify_passes_within_tolerances() -> None:
    writer = AsyncMock()
    writer.count_by_doc = AsyncMock(return_value=101)
    doc_id = uuid.uuid4()

    await verify_generation_counts(
        doc_id=doc_id,
        generation=2,
        pg_count=100,
        qdrant_writer=writer,
        collection="spark_docs",
        session=None,
        payload_sample_rate=0.0,
    )
