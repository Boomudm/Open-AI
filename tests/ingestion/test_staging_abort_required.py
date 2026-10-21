"""Phase 2 — staging cleanup failure is fail-closed (DLQ path)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.index.saga import IngestGenerationPlan, abort_staging_ingest


@pytest.mark.asyncio
async def test_abort_staging_ingest_raises_permanent_on_cleanup_failure() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    session = AsyncMock()
    qdrant_router = AsyncMock()

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
    ):
        with pytest.raises(PermanentIngestError) as exc_info:
            await abort_staging_ingest(
                doc_id=doc_id,
                plan=plan,
                qdrant_router=qdrant_router,
                session=session,
                collection="factory-knowledge",
            )
    assert exc_info.value.reason_code == "staging_cleanup_failed"


@pytest.mark.asyncio
async def test_abort_staging_ingest_is_idempotent_after_abort() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(
        ingest_saga_state="aborted",
        active_ingest_generation=1,
    )

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(return_value=None),
    ) as abort_mock:
        await abort_staging_ingest(
            doc_id=doc_id,
            plan=plan,
            qdrant_router=AsyncMock(),
            session=session,
            collection="factory-knowledge",
        )

    abort_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_abort_staging_ingest_skips_committed_generation() -> None:
    doc_id = uuid.uuid4()
    plan = IngestGenerationPlan(staging=3, active=2, is_reingest=True)
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(
        ingest_saga_state="purge_pending",
        active_ingest_generation=3,
    )

    with patch(
        "spark.ingestion.index.saga.IngestIndexSaga.abort",
        new=AsyncMock(return_value=None),
    ) as abort_mock:
        await abort_staging_ingest(
            doc_id=doc_id,
            plan=plan,
            qdrant_router=AsyncMock(),
            session=session,
            collection="factory-knowledge",
        )

    abort_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_error_handler_propagates_staging_cleanup_failure() -> None:
    from spark.ingestion.context import IngestContext, JobSummary
    from spark.ingestion.stages.runner import _handle_pipeline_error

    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={},
        config_raw={"default_route": "qdrant"},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    ctx.ingest_plan = IngestGenerationPlan(staging=2, active=1, is_reingest=True)
    ctx.chunks_written = 3
    summary = JobSummary(job_id=ctx.job_id, doc_id=doc_id, status="running")
    emit_progress = AsyncMock()

    cleanup_error = PermanentIngestError("staging_cleanup_failed", "qdrant unavailable")

    with patch(
        "spark.ingestion.stages.runner.abort_staging_ingest",
        new=AsyncMock(side_effect=cleanup_error),
    ):
        with pytest.raises(PermanentIngestError) as exc_info:
            await _handle_pipeline_error(
                cleanup_error,
                ctx=ctx,
                summary=summary,
                rows_total=10,
                rows_ok=3,
                rows_skipped=0,
                ingest_plan=ctx.ingest_plan,
                chunks_written=3,
                qdrant_router=AsyncMock(),
                qdrant_collection="factory-knowledge",
                emit_progress=emit_progress,
            )
    assert exc_info.value.reason_code == "staging_cleanup_failed"
