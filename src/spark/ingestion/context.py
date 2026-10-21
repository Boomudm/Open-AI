"""Explicit ingest pipeline context (replaces undocumented dict magic keys)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spark.ingestion.config_resolver import ResolvedIngestConfig
from spark.ingestion.parsers.base import ParsedRecord


@dataclass
class JobSummary:
    job_id: uuid.UUID
    doc_id: uuid.UUID
    status: str
    rows_total: int = 0
    rows_ok: int = 0
    rows_skipped: int = 0
    rows_skipped_ocr: int = 0
    error: str | None = None


@dataclass
class IngestContext:
    doc_id: uuid.UUID
    job_id: uuid.UUID
    factory_id: str | None
    machine_id: str | None
    document_type: str
    file_hash_sha256: str | None
    document_context: dict[str, Any]
    config_raw: dict[str, Any]
    file_path: Path
    resolved_config: ResolvedIngestConfig | None = None
    job_attempt_count: int = 1
    staging_generation: int | None = None
    is_reingest: bool = False
    budget: Any = None
    ingest_plan: Any = None
    chunks_written: int = 0
    qdrant_collection: str | None = None
    parse_warnings: list[dict[str, Any]] = field(default_factory=list)
    indexed_pages: set[int] = field(default_factory=set)

    @classmethod
    def build(
        cls,
        *,
        doc_id: uuid.UUID,
        job_id: uuid.UUID,
        document_type: str,
        file_path: Path,
        document_context: dict[str, Any],
        resolved: ResolvedIngestConfig,
        job_attempt_count: int = 1,
    ) -> IngestContext:
        document_context.setdefault("document_type", document_type)
        document_context.setdefault("document_category", resolved.raw.get("document_category"))
        document_context.setdefault("source_file", file_path.name)
        return cls(
            doc_id=doc_id,
            job_id=job_id,
            factory_id=document_context.get("factory_id"),
            machine_id=document_context.get("machine_id"),
            document_type=document_type,
            file_hash_sha256=document_context.get("file_hash_sha256"),
            document_context=document_context,
            config_raw=resolved.raw,
            resolved_config=resolved,
            file_path=file_path,
            job_attempt_count=job_attempt_count,
        )


@dataclass
class TrustScanState:
    enabled: bool = False
    version: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    max_risk_score: float = 0.0


@dataclass
class ParseStageResult:
    rows_total: int = 0


@dataclass
class TransformStageResult:
    qdrant_records: list[ParsedRecord] = field(default_factory=list)
    postgres_records: list[ParsedRecord] = field(default_factory=list)
    rows_ok: int = 0
    rows_skipped: int = 0
    rows_skipped_ocr: int = 0


@dataclass
class IndexStageResult:
    chunks_written: int = 0


@dataclass
class StageBuffers:
    qdrant: list[ParsedRecord] = field(default_factory=list)
    postgres: list[ParsedRecord] = field(default_factory=list)
