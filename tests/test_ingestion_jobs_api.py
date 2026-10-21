"""Tests for ingestion job upload metadata."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from spark.api.v1.endpoints.jobs import _job_to_out
from spark.db.models.ingestion import IngestionJob

JOB_ID = uuid.uuid4()
DOC_ID = uuid.uuid4()


def test_job_to_out_prefers_job_fields() -> None:
    job = MagicMock(spec=IngestionJob)
    job.job_id = JOB_ID
    job.doc_id = DOC_ID
    job.document_type = "machine_manual"
    job.original_filename = "upload.pdf"
    job.file_size_bytes = 2048
    job.factory_id = "F-01"
    job.machine_id = "MC-001"
    job.status = "queued"
    job.rows_total = 0
    job.rows_ok = 0
    job.rows_skipped = 0
    job.started_at = None
    job.finished_at = None
    job.created_at = None
    job.error_message = None

    out = _job_to_out(job, doc=None)
    assert out.original_filename == "upload.pdf"
    assert out.file_size_bytes == 2048
    assert out.factory_id == "F-01"
    assert out.machine_id == "MC-001"
    # Queued jobs report 5% so the UI shows activity instead of a stuck 0%.
    assert out.progress_percent == 5
    assert out.chunks_count == 0
    assert out.error_count == 0


def test_job_to_out_falls_back_to_document() -> None:
    job = MagicMock(spec=IngestionJob)
    job.job_id = JOB_ID
    job.doc_id = DOC_ID
    job.document_type = "knowledge_document"
    job.original_filename = None
    job.file_size_bytes = None
    job.factory_id = None
    job.machine_id = None
    job.status = "completed"
    job.rows_total = 10
    job.rows_ok = 10
    job.rows_skipped = 0
    job.started_at = None
    job.finished_at = None
    job.created_at = None
    job.error_message = None

    doc = MagicMock()
    doc.source_file = "legacy.xlsx"
    doc.file_size_bytes = 4096
    doc.factory_id = "F-02"
    doc.machine_id = "MC-002"
    doc.chunks_count = 12
    doc.page_count = 3
    doc.ingest_status = "completed"

    out = _job_to_out(job, doc=doc)
    assert out.original_filename == "legacy.xlsx"
    assert out.file_size_bytes == 4096
    assert out.factory_id == "F-02"
    assert out.machine_id == "MC-002"
    assert out.progress_percent == 100
    assert out.chunks_count == 12
    assert out.page_count == 3
    assert out.document_ingest_status == "completed"


def test_job_to_out_includes_operator_summary_fields() -> None:
    job = MagicMock(spec=IngestionJob)
    job.job_id = JOB_ID
    job.doc_id = DOC_ID
    job.document_type = "machine_manual"
    job.original_filename = "manual.pdf"
    job.file_size_bytes = 2048
    job.factory_id = "F-01"
    job.machine_id = "MC-001"
    job.status = "running"
    job.rows_total = 10
    job.rows_ok = 4
    job.rows_skipped = 1
    job.started_at = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    job.finished_at = datetime(2026, 6, 12, 10, 0, 5, tzinfo=timezone.utc)
    job.created_at = datetime(2026, 6, 12, 9, 59, tzinfo=timezone.utc)
    job.error_message = "alias_not_resolved: machine label"

    doc = MagicMock()
    doc.source_file = "manual.pdf"
    doc.file_size_bytes = 2048
    doc.factory_id = "F-01"
    doc.machine_id = "MC-001"
    doc.chunks_count = 7
    doc.page_count = 2
    doc.ingest_status = "partial"

    out = _job_to_out(
        job,
        doc=doc,
        error_count=2,
        last_error_code="alias_not_resolved",
        last_error_detail="machine label",
    )

    # Running percent is scaled into the 5-90 band (see _progress_percent):
    # rows_total grows while parsing streams, so the raw ratio is not honest.
    assert out.progress_percent == 47
    assert out.duration_seconds == 5.0
    assert out.error_count == 2
    assert out.last_error_code == "alias_not_resolved"
    assert out.last_error_detail == "machine label"
    assert out.chunks_count == 7
    assert out.page_count == 2
