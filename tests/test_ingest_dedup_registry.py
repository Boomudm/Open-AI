"""Dedup strategy registry tests (Phase 3)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.context import IngestContext
from spark.ingestion.dedup import (
    ReingestReplaceStrategy,
    SkipIfExistsStrategy,
    get_dedup_strategy,
    should_skip_row_with_meta,
)
from spark.ingestion.parsers.base import ParsedRecord


def test_registry_contains_both_strategies() -> None:
    assert isinstance(get_dedup_strategy("skip_if_exists"), SkipIfExistsStrategy)
    assert isinstance(get_dedup_strategy("reingest_replace"), ReingestReplaceStrategy)


@pytest.mark.asyncio
async def test_reingest_replace_never_skips() -> None:
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id="MC-1",
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={"file_hash_sha256": "abc"},
        config_raw={"dedup": {"strategy": "reingest_replace", "by": ["file_hash_sha256"]}},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    rec = ParsedRecord(route="qdrant", payload={}, text_for_embedding="chunk")
    decision = await ReingestReplaceStrategy().should_skip(rec, ctx, MagicMock())
    assert decision.skip is False


@pytest.mark.asyncio
async def test_skip_if_exists_ocr_flag() -> None:
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256=None,
        document_context={},
        config_raw={"dedup": {"strategy": "skip_if_exists", "by": ["page_content"]}},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    rec = ParsedRecord(route="qdrant", payload={"_ocr_skipped": True}, text_for_embedding="")
    session = AsyncMock()
    decision = await should_skip_row_with_meta(rec, ctx, session, seen_chunk_hashes=set())
    assert decision.skip is True
    assert decision.is_ocr_skip is True
