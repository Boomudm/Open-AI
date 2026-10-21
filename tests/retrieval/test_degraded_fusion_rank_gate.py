"""Phase 7 — rank-based degraded fusion gate."""

from __future__ import annotations

import pytest

from spark.retrieval.degraded_policy import apply_degraded_rerank
from spark.retrieval.degraded_types import raw_fusion_score
from spark.retrieval.intent.router import QueryIntent
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.degraded_floors_config import load_degraded_fusion_floors
from spark.retrieval.rerank.gate import apply_rerank_gate
from spark.retrieval.safety.safety_intent import SafetyIntentKind


def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="step one",
        score=score,
        vector_score=score,
        fusion_score=score,
        payload={"chunk_id": "x"},
    )


def test_apply_degraded_rerank_preserves_raw_scores() -> None:
    docs = [_doc(0.2), _doc(0.5), _doc(0.3)]
    ordered, policy = apply_degraded_rerank(
        docs,
        intent=QueryIntent.GENERAL,
        safety_intent_kind=SafetyIntentKind.NONE.value,
        ce_available=False,
    )
    assert policy.value == "ce_timeout_fusion_rank"
    assert raw_fusion_score(ordered[0]) == 0.5
    assert raw_fusion_score(ordered[0]) != 1.0


def test_degraded_fusion_floors_yaml_loads() -> None:
    cfg = load_degraded_fusion_floors()
    general = cfg.for_intent(QueryIntent.GENERAL)
    assert general.min_raw_fusion == pytest.approx(0.18)
    assert general.max_fusion_rank == 3


def test_rank_gap_requirement_blocks_tight_cluster_below_floor() -> None:
    """Tight cluster below raw fusion floor must fail even when rank is 1."""
    docs = [_doc(0.17), _doc(0.16), _doc(0.15)]
    result = apply_rerank_gate(docs, question="general query", degraded=True)
    assert result.passed is False
