from __future__ import annotations

from spark.eval.rag_metrics import compute_rag_metrics, per_document_type_breakdown


class _Score:
    def __init__(
        self,
        *,
        mode: str = "rag",
        passed: bool = True,
        expected_sources: int = 0,
        returned_sources: int = 0,
        matched_sources: int = 0,
        issues: list[str] | None = None,
        output: dict | None = None,
    ) -> None:
        self.mode = mode
        self.passed = passed
        self.expected_sources = expected_sources
        self.returned_sources = returned_sources
        self.matched_sources = matched_sources
        self.issues = issues or []
        self.output = output or {}


def test_compute_rag_metrics_empty() -> None:
    metrics = compute_rag_metrics([])
    assert metrics["rag_case_count"] == 0
    assert metrics["context_precision_pct"] == 100.0


def test_compute_rag_metrics_forbidden_violation() -> None:
    row = _Score(
        expected_sources=1,
        returned_sources=2,
        matched_sources=1,
        issues=["forbidden_sources_returned=['repair.xlsx']"],
    )
    metrics = compute_rag_metrics([row])
    assert metrics["forbidden_source_violations"] == 1


def test_per_document_type_groups_none_bucket() -> None:
    row = _Score(output={"sources": []})
    breakdown = per_document_type_breakdown([row])
    assert "_none" in breakdown
