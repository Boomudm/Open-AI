"""Partial-ingest / quality-SLO policy: ingest is tag-only for every document type.

Product decision (2026-07): a document that indexed most of its pages must
still become answerable — the old default DLQ'd whole vendor manuals when a
few rows skipped, leaving users with nothing. This was later extended
(2026-07) to drop hard-blocking entirely, including for safety document types
(sop/machine_manual/safety_certificate): quality concerns are tagged on the
document for review, never used to refuse ingest or the index swap.
"""

from __future__ import annotations

from spark.ingestion.context import TransformStageResult
from spark.ingestion.quality.slo import (
    build_quality_report,
    enforce_finalize_slos,
    evaluate_slos,
)


def _report(rows_ok: int = 8, rows_skipped: int = 2, pages: int = 10):
    return build_quality_report(
        document_context={"page_count": pages},
        transform=TransformStageResult(rows_ok=rows_ok, rows_skipped=rows_skipped),
        rows_total=rows_ok + rows_skipped,
        indexed_pages=set(range(1, rows_ok + 1)),
    )


def test_partial_swap_allowed_by_default_for_all_types() -> None:
    for document_type in ("machine_manual", "sop", "io_mapping", "custom_unknown_doc_type"):
        verdict = evaluate_slos(_report(), document_type)
        assert verdict.partial_swap_allowed is True, document_type


def test_enforce_finalize_slos_accepts_partial_status() -> None:
    failure = enforce_finalize_slos(
        document_type="machine_manual",
        job_status="partial",
        report=_report(rows_ok=4, rows_skipped=1, pages=5),
    )
    assert failure is None


def test_safety_types_no_longer_force_full_ingest(monkeypatch) -> None:
    """Safety types get no special hard-block treatment anymore — tag-only applies uniformly."""
    import spark.ingestion.quality.slo as slo_mod

    monkeypatch.setattr(
        slo_mod, "safety_document_types", lambda: frozenset({"machine_manual"})
    )
    verdict = evaluate_slos(_report(), "machine_manual")
    assert verdict.partial_swap_allowed is True

    failure = enforce_finalize_slos(
        document_type="machine_manual",
        job_status="partial",
        report=_report(rows_ok=1, rows_skipped=9, pages=10),
    )
    assert failure is None
