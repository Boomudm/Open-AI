"""Chaos — CE outage during soak must abstain or extractive-only on safety paths."""

from __future__ import annotations

import pytest

from spark.retrieval.degraded_policy import apply_degraded_rerank
from spark.retrieval.degraded_types import DegradedRetrievalPolicy
from spark.retrieval.intent.router import QueryIntent
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.safety.safety_intent import SafetyIntentKind


def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="LOTO lockout breaker step",
        score=score,
        vector_score=score,
        fusion_score=score,
        payload={"chunk_id": "c1", "document_type": "sop"},
    )


@pytest.mark.chaos
def test_ce_outage_weak_fusion_abstains_not_grounded_llm() -> None:
    _, policy = apply_degraded_rerank(
        [_doc(0.08), _doc(0.07)],
        intent=QueryIntent.SAFETY_LOTO,
        safety_intent_kind=SafetyIntentKind.LOTO.value,
        ce_available=False,
    )
    assert policy == DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN


@pytest.mark.chaos
def test_ce_outage_strong_fusion_extractive_only() -> None:
    _, policy = apply_degraded_rerank(
        [_doc(0.55), _doc(0.20)],
        intent=QueryIntent.SAFETY_LOTO,
        safety_intent_kind=SafetyIntentKind.LOTO.value,
        ce_available=False,
    )
    assert policy == DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY


@pytest.mark.chaos
def test_ce_outage_non_safety_uses_rank_gate_not_abstain() -> None:
    _, policy = apply_degraded_rerank(
        [_doc(0.55), _doc(0.20)],
        intent=QueryIntent.GENERAL,
        safety_intent_kind="none",
        ce_available=False,
    )
    assert policy == DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK
