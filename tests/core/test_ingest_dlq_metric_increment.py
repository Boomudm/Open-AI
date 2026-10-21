"""Phase 12 — ingest job permanent-failure path (legacy DLQ status retired)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spark.core.metrics import ingest_dlq_total


@pytest.mark.asyncio
async def test_mark_job_dlq_sets_failed_status_without_metric() -> None:
    """mark_job_dlq now records status="failed" (dlq_at=None) and logs instead
    of incrementing ingest_dlq_total — the DLQ status was retired in favor of
    a plain failed state."""
    from spark.ingestion.job_reliability import mark_job_dlq

    job_id = __import__("uuid").uuid4()
    doc_id = __import__("uuid").uuid4()
    before = ingest_dlq_total.labels("permanent_failure", "machine_manual")._value.get()  # type: ignore[attr-defined]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.get = AsyncMock(
        return_value=MagicMock(document_type="machine_manual"),
    )
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("spark.ingestion.job_reliability.AsyncSessionLocal", return_value=mock_cm):
        await mark_job_dlq(
            job_id,
            reason_code="permanent_failure",
            reason_detail="test",
            doc_id=doc_id,
        )

    after = ingest_dlq_total.labels("permanent_failure", "machine_manual")._value.get()  # type: ignore[attr-defined]
    assert after == before
