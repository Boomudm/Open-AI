"""Chaos — quarantine must capture full document, not partial batch."""

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
    text = f"chunk-{index}"
    return ParsedRecord(route="qdrant", payload={"page_content": text}, text_for_embedding=text)


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_quarantine_rejects_incomplete_document() -> None:
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={"source_file": "manual.pdf"},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    accumulator = DocumentAccumulator(ctx.doc_id)
    accumulator.append_batch([_record(i) for i in range(3)])
    outcome = TrustStageOutcome(kind="quarantine", trust_state=TrustScanState(enabled=True))

    with pytest.raises(PermanentIngestError) as exc_info:
        await finalize_quarantine(
            ctx,
            AsyncMock(),
            accumulator=accumulator,
            rows_total=10,
            trust_state=outcome.trust_state,
            trust_outcome=outcome,
        )
    assert exc_info.value.reason_code == "quarantine_incomplete"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_quarantine_persists_full_accumulated_document() -> None:
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="sop",
        file_hash_sha256="abc",
        document_context={"source_file": "sop.pdf"},
        config_raw={},
        file_path=__import__("pathlib").Path("sop.pdf"),
    )
    accumulator = DocumentAccumulator(ctx.doc_id)
    for index in range(25):
        accumulator.append_batch([_record(index)])

    outcome = TrustStageOutcome(kind="quarantine", trust_state=TrustScanState(enabled=True))
    with patch(
        "spark.ingestion.stages.trust_stage.save_quarantine_artifact",
        new=AsyncMock(return_value="s3://quarantine/full.json"),
    ) as save_mock:
        await finalize_quarantine(
            ctx,
            AsyncMock(),
            accumulator=accumulator,
            rows_total=25,
            trust_state=outcome.trust_state,
            trust_outcome=outcome,
        )

    saved = save_mock.await_args.kwargs["records"]
    assert len(saved) == 25
