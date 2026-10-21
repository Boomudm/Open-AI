"""Streaming ingest memory bounds."""

from __future__ import annotations

import tracemalloc
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.budget import ResourceBudgetTracker, budget_from_config
from spark.ingestion.context import IngestContext
from spark.ingestion.parsers.base import ParsedRecord, ParserPlugin
from spark.ingestion.stages.parse_stage import parse_batched


class CountingParser(ParserPlugin):
    name = "counting"
    supported_extensions = (".txt",)

    def __init__(self, total: int) -> None:
        self.total = total

    async def parse(self, file_path: Path, config: dict) -> AsyncIterator[ParsedRecord]:
        del file_path, config
        for index in range(self.total):
            text = f"chunk-{index}-" + ("x" * 256)
            yield ParsedRecord(
                route="qdrant",
                payload={"page_content": text, "chunk_index": index, "page_count": self.total},
                text_for_embedding=text,
            )


@pytest.mark.asyncio
async def test_parse_batched_peak_memory_bounded() -> None:
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]

    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={},
        config_raw={"budget": {"max_chunks": 20000}},
        file_path=Path("manual.txt"),
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    parser = CountingParser(total=10_000)
    budget = ResourceBudgetTracker(budget_from_config(ctx.config_raw))

    peak_delta = 0
    batch_count = 0
    async for batch, rows_total in parse_batched(
        ctx,
        session,
        parser,
        budget=budget,
        batch_size=64,
    ):
        batch_count += 1
        current, _peak = tracemalloc.get_traced_memory()
        peak_delta = max(peak_delta, current - baseline)
        assert len(batch) <= 64
        del batch

    tracemalloc.stop()

    assert rows_total == 10_000
    assert batch_count == 157
    assert peak_delta < 5_000_000
