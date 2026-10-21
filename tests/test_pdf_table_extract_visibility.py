"""Phase 6 — PDF table extraction failures surface in job events."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from spark.ingestion.context import IngestContext
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.stages.parse_stage import parse_batched


@pytest.mark.asyncio
async def test_pdf_table_extract_failure_emits_warning_event() -> None:
    ctx = IngestContext(
        doc_id=uuid4(),
        job_id=uuid4(),
        factory_id="f-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={"parser": "pdf"},
        config_raw={"document_type": "machine_manual"},
        file_path=MagicMock(),
        resolved_config=None,
    )

    class FakeParser:
        async def parse(self, file_path, config):
            from spark.ingestion.parse.warnings import ParseWarningCollector, TableExtractWarning

            collector = config.get("_parse_warnings")
            assert isinstance(collector, ParseWarningCollector)
            collector.add(
                TableExtractWarning(
                    file="manual.pdf",
                    error="pdfplumber table extract failed",
                    page_count=12,
                )
            )
            yield ParsedRecord(route="qdrant", payload={"page_count": 1, "chunk_index": 0, "page_content": "x"})

    session = AsyncMock()
    batches = [
        batch
        async for batch, _total in parse_batched(
            ctx,
            session,
            FakeParser(),
            budget=MagicMock(record_page_count=MagicMock(), record_chunk=MagicMock()),
        )
    ]
    assert batches
    added_events = [call.args[0] for call in session.add.call_args_list]
    codes = [getattr(event, "code", None) for event in added_events]
    assert "table_extract_warning" in codes
    assert ctx.parse_warnings
    assert ctx.parse_warnings[0]["code"] == "table_extract_warning"
