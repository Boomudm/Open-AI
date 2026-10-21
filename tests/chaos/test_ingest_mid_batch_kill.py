"""Chaos — abrupt ingest termination mid-batch must not commit partial swap."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.context import IngestContext
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.index.saga import IngestGenerationPlan, abort_staging_ingest


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_mid_batch_kill_triggers_staging_abort_not_swap() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    session = AsyncMock()

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(return_value=None),
    ) as abort_mock:
        await abort_staging_ingest(
            doc_id=doc_id,
            plan=plan,
            qdrant_router=AsyncMock(),
            session=session,
            collection="spark_docs",
        )

    abort_mock.assert_awaited_once()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_mid_batch_kill_on_cleanup_failure_routes_dlq() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(side_effect=RuntimeError("worker killed")),
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


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_pipeline_error_mid_batch_invokes_abort() -> None:
    from spark.ingestion.context import JobSummary
    from spark.ingestion.errors import TransientIngestError
    from spark.ingestion.stages.runner import _handle_pipeline_error

    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id="MC-001",
        document_type="machine_manual",
        file_hash_sha256="deadbeef",
        document_context={},
        config_raw={"default_route": "qdrant"},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    ctx.ingest_plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    ctx.chunks_written = 5
    summary = JobSummary(job_id=ctx.job_id, doc_id=doc_id, status="running")
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()

    class _SessionCtx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *args):
            return False

    exc = TransientIngestError("worker_killed", "simulated SIGKILL mid-batch")

    with patch(
        "spark.ingestion.stages.runner.abort_staging_ingest",
        new=AsyncMock(return_value=None),
    ) as abort_mock, patch(
        "spark.ingestion.stages.runner.AsyncSessionLocal",
        return_value=_SessionCtx(),
    ), patch(
        "spark.ingestion.stages.runner.append_ingestion_event",
        new=AsyncMock(),
    ), patch(
        "spark.ingestion.stages.runner.clear_idempotency_key",
        new=AsyncMock(),
    ), pytest.raises(TransientIngestError):
        await _handle_pipeline_error(
            exc,
            ctx=ctx,
            summary=summary,
            rows_total=20,
            rows_ok=5,
            rows_skipped=0,
            ingest_plan=ctx.ingest_plan,
            chunks_written=5,
            qdrant_router=AsyncMock(),
            qdrant_collection="spark_docs",
            emit_progress=AsyncMock(),
        )

    abort_mock.assert_awaited_once()
