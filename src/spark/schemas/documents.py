from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from spark.schemas.openapi_examples import INGEST_FILE_RESPONSE, INGESTION_ERROR, INGESTION_JOB


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doc_id: UUID
    factory_id: str | None
    machine_id: str | None
    document_category: str
    document_type: str
    title: str | None
    language: str
    revision: str | None
    effective_date: date | None
    expiry_date: date | None
    source_file: str
    original_filename: str | None = None
    mime_type: str | None = None
    file_hash_sha256: str | None = None
    file_size_bytes: int | None
    page_count: int | None
    ingest_status: str
    chunks_count: int
    retrieval_enabled: bool = True
    quarantine_reason: str | None = None
    policy_scan_version: str | None = None
    content_risk_score: float | None = None
    released_at: datetime | None = None
    extra_metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    visible_position_ids: list[UUID] = Field(default_factory=list)


class DocumentVisibilityUpdate(BaseModel):
    visible_position_ids: list[UUID] = Field(default_factory=list)


class IngestFileResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [INGEST_FILE_RESPONSE]})

    job_id: UUID
    doc_id: UUID
    status: str
    celery_task_id: str | None = None


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [INGESTION_JOB]})

    job_id: UUID
    doc_id: UUID | None
    document_type: str
    original_filename: str | None = None
    file_size_bytes: int | None = None
    factory_id: str | None = None
    machine_id: str | None = None
    status: str
    rows_total: int
    rows_ok: int
    rows_skipped: int
    progress_percent: int = 0
    chunks_count: int = 0
    page_count: int | None = None
    document_ingest_status: str | None = None
    error_count: int = 0
    last_error_code: str | None = None
    last_error_detail: str | None = None
    duration_seconds: float | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None = None
    error_message: str | None
    attempt_count: int = 0
    dlq_at: datetime | None = None
    next_retry_at: datetime | None = None


class IngestionErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [INGESTION_ERROR]})

    error_id: UUID
    job_id: UUID
    row_number: int | None
    chunk_index: int | None
    reason_code: str | None
    reason_detail: str | None
    raw_payload: dict[str, Any] | None
    created_at: datetime
