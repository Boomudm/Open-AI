"""Phase 12 — semantic Prometheus labels."""

from __future__ import annotations

import inspect

from spark.core.metrics import rag_query_seconds
from spark.retrieval.service import _observe_rag_query_metrics


def test_rag_query_seconds_supports_degraded_label() -> None:
    metric_names = rag_query_seconds._labelnames  # type: ignore[attr-defined]
    assert "intent" in metric_names
    assert "degraded" in metric_names


def test_observe_rag_query_metrics_uses_intent_not_factual() -> None:
    source = inspect.getsource(_observe_rag_query_metrics)
    assert '"factual"' not in source
    assert "intent_label" in source
