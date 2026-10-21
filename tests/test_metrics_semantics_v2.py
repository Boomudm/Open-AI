"""Metrics semantics v2 — query total vs scope broadening (remediation v2 Phase 1)."""

from __future__ import annotations

from spark.core.metrics import rag_query_total, rag_scope_broadened_total
from spark.retrieval.service import _observe_rag_query_metrics


def _record_rag_query_metrics(fallback_level: int) -> None:
    _observe_rag_query_metrics(
        fallback_level=fallback_level,
        started_at=0.0,
        intent="unknown",
        degraded=False,
    )


def _counter_value(counter, *, level: str = "0") -> float:
    return float(counter.labels(fallback_level=level)._value.get())


def test_success_level_zero_increments_query_not_scope_broadened() -> None:
    before_query = _counter_value(rag_query_total, level="0")
    before_scope = _counter_value(rag_scope_broadened_total, level="0")
    _record_rag_query_metrics(0)
    assert _counter_value(rag_query_total, level="0") == before_query + 1.0
    assert _counter_value(rag_scope_broadened_total, level="0") == before_scope


def test_fallback_level_positive_increments_both() -> None:
    before_query = _counter_value(rag_query_total, level="2")
    before_scope = _counter_value(rag_scope_broadened_total, level="2")
    _record_rag_query_metrics(2)
    assert _counter_value(rag_query_total, level="2") == before_query + 1.0
    assert _counter_value(rag_scope_broadened_total, level="2") == before_scope + 1.0
