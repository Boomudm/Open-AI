"""Phase 2 — full-document quarantine artifact on mid-stream trust hit."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.context import IngestContext, TrustScanState
from spark.ingestion.document_accumulator import DocumentAccumulator
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.stages.trust_stage import TrustStageOutcome, finalize_quarantine


def _record(index: int) -> ParsedRecord:
    text = f"row-{index}"
    return ParsedRecord(route="qdrant", payload={"page_content": text}, text_for_embedding=text)


@pytest.mark.asyncio
async def test_finalize_quarantine_requires_full_document_count() -> None:
    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={"source_file": "manual.pdf"},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    accumulator = DocumentAccumulator(doc_id)
    for index in range(5):
        accumulator.append_batch([_record(index)])

    session = AsyncMock()
    outcome = TrustStageOutcome(kind="quarantine", trust_state=TrustScanState(enabled=True))

    with pytest.raises(PermanentIngestError) as exc_info:
        await finalize_quarantine(
            ctx,
            session,
            accumulator=accumulator,
            rows_total=10,
            trust_state=outcome.trust_state,
            trust_outcome=outcome,
        )
    assert exc_info.value.reason_code == "quarantine_incomplete"


@pytest.mark.asyncio
async def test_finalize_quarantine_persists_all_accumulated_records() -> None:
    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={"source_file": "manual.pdf"},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    accumulator = DocumentAccumulator(doc_id)
    for index in range(10):
        accumulator.append_batch([_record(index)])

    session = AsyncMock()
    session.execute = AsyncMock()
    outcome = TrustStageOutcome(kind="quarantine", trust_state=TrustScanState(enabled=True))

    with patch(
        "spark.ingestion.stages.trust_stage.save_quarantine_artifact",
        new=AsyncMock(return_value="s3://quarantine/full.json"),
    ) as save_mock:
        result = await finalize_quarantine(
            ctx,
            session,
            accumulator=accumulator,
            rows_total=10,
            trust_state=outcome.trust_state,
            trust_outcome=outcome,
        )

    assert result.kind == "quarantine"
    save_mock.assert_awaited_once()
    saved_records = save_mock.await_args.kwargs["records"]
    assert len(saved_records) == 10


@pytest.mark.asyncio
async def test_orchestrator_drains_remaining_parse_batches_on_quarantine() -> None:
    from spark.ingestion.orchestrator import _drain_parse_into_accumulator

    doc_id = uuid.uuid4()
    accumulator = DocumentAccumulator(doc_id)

    async def parse_iter():
        for batch_index in range(10):
            yield [_record(batch_index * 2), _record(batch_index * 2 + 1)], 20

    iterator = parse_iter().__aiter__()
    first_batch, _ = await iterator.__anext__()
    accumulator.append_batch(first_batch)

    rows_total = await _drain_parse_into_accumulator(iterator, accumulator)
    assert rows_total == 20
    assert accumulator.record_count() == 20
