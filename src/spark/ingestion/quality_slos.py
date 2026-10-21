"""Safety document ingest quality SLO gates — re-exports Phase 7 engine."""

from __future__ import annotations

from typing import Any

from spark.ingestion.context import TransformStageResult
from spark.ingestion.quality.slo import (
    IngestQualityReport,
    build_quality_report,
    enforce_finalize_slos,
    evaluate_slos,
    load_quality_slos,
    safety_document_types,
)


def max_skipped_ratio(document_type: str) -> float | None:
    slos = load_quality_slos()
    default_ratio = slos.get("default_max_skipped_ratio")
    per_type = (slos.get("per_document_type") or {}).get(document_type, {})
    ratio = per_type.get("max_skipped_ratio", default_ratio)
    return float(ratio) if ratio is not None else None


def enforce_safety_swap_policy(
    *,
    document_type: str,
    job_status: str,
    rows_ok: int,
    rows_skipped: int,
    rows_skipped_ocr: int = 0,
    rows_total: int | None = None,
    document_context: dict[str, Any] | None = None,
    parse_warnings: list[dict[str, Any]] | None = None,
    indexed_pages: set[int] | None = None,
) -> tuple[str, str] | None:
    """Return (reason_code, detail) when safety docs must not commit a partial swap."""
    transform = TransformStageResult(
        rows_ok=rows_ok,
        rows_skipped=rows_skipped,
        rows_skipped_ocr=rows_skipped_ocr,
    )
    report = build_quality_report(
        document_context=document_context or {},
        transform=transform,
        rows_total=rows_total or (rows_ok + rows_skipped),
        parse_warnings=parse_warnings,
        indexed_pages=indexed_pages,
    )
    return enforce_finalize_slos(
        document_type=document_type,
        job_status=job_status,
        report=report,
    )


__all__ = [
    "IngestQualityReport",
    "build_quality_report",
    "enforce_finalize_slos",
    "enforce_safety_swap_policy",
    "evaluate_slos",
    "load_quality_slos",
    "max_skipped_ratio",
    "safety_document_types",
]
