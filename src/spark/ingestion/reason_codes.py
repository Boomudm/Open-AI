"""Stable ingest reason codes for ops dashboards, retry policy, and DLQ routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReasonCode(str, Enum):
    UNKNOWN = "unknown"
    PIPELINE_FAILED = "pipeline_failed"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    CONFIG_PROFILE_NOT_FOUND = "config_profile_not_found"
    VALIDATION_FAILED = "validation_failed"
    DUPLICATE_JOB_IN_PROGRESS = "duplicate_job_in_progress"
    VALIDATION_FORMAT = "validation_format"
    CONTENT_POLICY_BLOCK = "content_policy_block"
    ALIAS_NOT_RESOLVED = "alias_not_resolved"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    NO_INDEXABLE_CHUNKS = "no_indexable_chunks"
    OCR_QUALITY_INSUFFICIENT = "ocr_quality_insufficient"
    VISION_BACKEND_UNAVAILABLE = "vision_backend_unavailable"
    POSTGRES_TABLE_NOT_ALLOWED = "postgres_table_not_allowed"
    QDRANT_TIMEOUT = "qdrant_timeout"
    QDRANT_UNAVAILABLE = "qdrant_unavailable"
    EMBED_TRANSIENT = "embed_transient"
    STORAGE_READ_FAILED = "storage_read_failed"
    DB_TRANSIENT = "db_transient"
    BUDGET_EXCEEDED = "budget_exceeded"
    QUALITY_SLO_BREACH = "quality_slo_breach"
    DUPLICATE_ROW = "duplicate_row"
    ALIAS_WARN = "alias_warn"

    @property
    def is_transient(self) -> bool:
        return self in _TRANSIENT

    @property
    def operator_action(self) -> str:
        return _OPERATOR_ACTION.get(self, "Review job error log and ingestion_events.")


_TRANSIENT: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.QDRANT_TIMEOUT,
        ReasonCode.QDRANT_UNAVAILABLE,
        ReasonCode.EMBED_TRANSIENT,
        ReasonCode.STORAGE_READ_FAILED,
        ReasonCode.DB_TRANSIENT,
        # Backend down / out of quota — the drawing itself is fine, so a retry is
        # the right response rather than burying the doc as a permanent failure.
        ReasonCode.VISION_BACKEND_UNAVAILABLE,
    }
)

_OPERATOR_ACTION: dict[ReasonCode, str] = {
    ReasonCode.CONTENT_POLICY_BLOCK: "Review policy findings; do not release without admin review.",
    ReasonCode.DUPLICATE_JOB_IN_PROGRESS: "Wait for the active ingest job on this document to finish.",
    ReasonCode.VALIDATION_FAILED: "Fix upload metadata or source file validation errors and re-upload.",
    ReasonCode.UNKNOWN: "Inspect stack trace; unclassified errors are permanent — replay only after fix.",
    ReasonCode.BUDGET_EXCEEDED: "Reduce document size or raise budget limits in ingestion YAML.",
    ReasonCode.QUALITY_SLO_BREACH: "Re-upload a complete source file; safety docs cannot commit partial swaps.",
    ReasonCode.CONFIG_PROFILE_NOT_FOUND: "Fix document type YAML or factory config override.",
    ReasonCode.VISION_BACKEND_UNAVAILABLE: (
        "Vision model returned nothing for every diagram page — check the vision_extract "
        "profile's backend/quota (e.g. KKU daily limit), then retry. The previous "
        "generation is still being served."
    ),
    ReasonCode.ALIAS_NOT_RESOLVED: "Resolve machine/component alias or fix source spreadsheet.",
    ReasonCode.OCR_QUALITY_INSUFFICIENT: "Re-scan document or upload higher-quality source.",
    ReasonCode.POSTGRES_TABLE_NOT_ALLOWED: "Add table to postgres allowlist manifest or fix config.",
    ReasonCode.NO_EXTRACTABLE_TEXT: "Upload a text-bearing file or enable OCR for scanned PDFs.",
}


@dataclass(frozen=True)
class ClassifiedReason:
    code: ReasonCode
    detail: str
    transient: bool

    @property
    def reason_code(self) -> str:
        return self.code.value
