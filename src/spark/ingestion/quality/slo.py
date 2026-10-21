"""Content quality SLO evaluation for ingest finalize (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.ingestion.context import TransformStageResult

_SLO_PATH = Path(__file__).resolve().parents[4] / "configs" / "ingest_quality_slos.yaml"


@lru_cache(maxsize=1)
def load_quality_slos() -> dict[str, Any]:
    if not _SLO_PATH.is_file():
        return {}
    with _SLO_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def safety_document_types() -> frozenset[str]:
    raw = load_quality_slos().get("safety_document_types") or []
    return frozenset(str(item) for item in raw)


@dataclass
class IngestQualityReport:
    pages_total: int
    pages_indexed: int
    ocr_rejected: int
    tables_dropped: int
    skip_ratio: float
    rows_total: int = 0
    rows_ok: int = 0
    rows_skipped: int = 0


@dataclass
class SLOVerdict:
    passed: bool
    breaches: list[str] = field(default_factory=list)
    partial_swap_allowed: bool = False


def build_quality_report(
    *,
    document_context: dict[str, Any],
    transform: TransformStageResult,
    rows_total: int,
    parse_warnings: list[dict[str, Any]] | None = None,
    indexed_pages: set[int] | None = None,
) -> IngestQualityReport:
    pages_total = int(document_context.get("page_count") or 0)
    if indexed_pages:
        pages_indexed = len(indexed_pages)
    elif pages_total:
        pages_indexed = max(0, pages_total - transform.rows_skipped_ocr)
    else:
        pages_indexed = transform.rows_ok

    warnings = parse_warnings or []
    tables_dropped = sum(1 for item in warnings if item.get("code") == "table_extract_warning")
    skip_ratio = (transform.rows_skipped / rows_total) if rows_total > 0 else 0.0

    return IngestQualityReport(
        pages_total=pages_total,
        pages_indexed=pages_indexed,
        ocr_rejected=transform.rows_skipped_ocr,
        tables_dropped=tables_dropped,
        skip_ratio=skip_ratio,
        rows_total=rows_total,
        rows_ok=transform.rows_ok,
        rows_skipped=transform.rows_skipped,
    )


def _type_slos(document_type: str) -> dict[str, Any]:
    slos = load_quality_slos()
    per_type = slos.get("per_document_type") or {}
    cfg = per_type.get(document_type) or {}
    return cfg if isinstance(cfg, dict) else {}


def _slo_metric_name(breach: str) -> str:
    token = breach.split()[0] if breach else "unknown"
    return token.replace(":", "_")[:64]


def evaluate_slos(report: IngestQualityReport, document_type: str) -> SLOVerdict:
    cfg = _type_slos(document_type)
    breaches: list[str] = []

    if report.pages_total > 0:
        indexed_ratio = report.pages_indexed / report.pages_total
        min_ratio = cfg.get("min_indexed_page_ratio")
        if min_ratio is not None and indexed_ratio < float(min_ratio):
            breaches.append(
                f"indexed_page_ratio {indexed_ratio:.1%} below min {float(min_ratio):.1%}"
            )

    denominator = report.pages_total or report.rows_total or 1
    if report.ocr_rejected > 0:
        ocr_ratio = report.ocr_rejected / denominator
        max_ocr = cfg.get("max_ocr_reject_ratio")
        if max_ocr is not None and ocr_ratio > float(max_ocr):
            breaches.append(
                f"ocr_reject_ratio {ocr_ratio:.1%} exceeds max {float(max_ocr):.1%}"
            )

    max_skipped = cfg.get("max_skipped_ratio")
    if max_skipped is None and document_type in safety_document_types():
        max_skipped = load_quality_slos().get("default_max_skipped_ratio")
    if max_skipped is not None and report.skip_ratio > float(max_skipped):
        breaches.append(
            f"skip_ratio {report.skip_ratio:.1%} exceeds max {float(max_skipped):.1%}"
        )

    partial_allowed = cfg.get("partial_swap_allowed")
    if partial_allowed is None:
        global_default = load_quality_slos().get("partial_swap_allowed")
        # Default ALLOWED: a document that indexed most of its pages must
        # still become answerable — refusing the swap because some rows were
        # skipped previously DLQ'd whole real vendor manuals and left users
        # with nothing. Factories can still opt back in per type or globally
        # via configs/ingest_quality_slos.yaml.
        partial_allowed = True if global_default is None else bool(global_default)

    if breaches:
        from spark.core.metrics import ingest_quality_slo_breach_total

        for breach in breaches:
            ingest_quality_slo_breach_total.labels(_slo_metric_name(breach)).inc()

    return SLOVerdict(
        passed=not breaches,
        breaches=breaches,
        partial_swap_allowed=bool(partial_allowed),
    )


def enforce_finalize_slos(
    *,
    document_type: str,
    job_status: str,
    report: IngestQualityReport,
) -> tuple[str, str] | None:
    """Quality SLOs are tag-only: breaches are logged/tagged on the document,
    never used to block finalize or refuse the index swap."""
    return None
