"""Generation-scoped dedup during re-ingest."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.context import IngestContext
from spark.ingestion.dedup import SkipIfExistsStrategy
from spark.ingestion.parsers.base import ParsedRecord


@pytest.mark.asyncio
async def test_skip_if_exists_scopes_to_staging_generation() -> None:
    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={},
        config_raw={"dedup": {"by": ["page_content"], "strategy": "skip_if_exists"}},
        file_path=MagicMock(),
        staging_generation=2,
        is_reingest=True,
    )
    record = ParsedRecord(
        route="qdrant",
        payload={"page_content": "live chunk text"},
        text_for_embedding="live chunk text",
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    strategy = SkipIfExistsStrategy()
    decision = await strategy.should_skip(record, ctx, session)

    assert decision.skip is False
    where_clause = session.scalar.await_args.args[0].whereclause
    assert where_clause is not None
    where_text = str(where_clause)
    assert "ingest_generation" in where_text


@pytest.mark.asyncio
async def test_skip_if_exists_finds_duplicate_in_staging_only() -> None:
    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={},
        config_raw={"dedup": {"by": ["page_content"], "strategy": "skip_if_exists"}},
        file_path=MagicMock(),
        staging_generation=2,
        is_reingest=True,
    )
    record = ParsedRecord(
        route="qdrant",
        payload={"page_content": "staging duplicate"},
        text_for_embedding="staging duplicate",
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=uuid.uuid4())

    strategy = SkipIfExistsStrategy()
    decision = await strategy.should_skip(record, ctx, session)

    assert decision.skip is True
    assert decision.reason == "duplicate_chunk_content"
