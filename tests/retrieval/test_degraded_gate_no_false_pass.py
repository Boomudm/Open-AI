"""Phase 7 — degraded rerank gate must not false-pass weak fusion scores."""

from __future__ import annotations

import pytest

from spark.retrieval.intent.router import IntentRouter
from spark.retrieval.degraded_types import DegradedRetrievalPolicy
from spark.retrieval.rerank.gate import apply_rerank_gate
from spark.retrieval.models import RetrievedDoc


def _doc(score: float, *, chunk_id: str = "c1") -> RetrievedDoc:
    return RetrievedDoc(
        page_content="bearing temperature limit",
        score=score,
        vector_score=score,
        fusion_score=score,
        payload={"chunk_id": chunk_id, "document_type": "machine_manual"},
    )


def test_weak_fusion_batch_fails_degraded_gate_without_calibration() -> None:
    """CE timeout + weak fusion must fail — never normalize to 1.0."""
    docs = [
        _doc(0.12, chunk_id="c1"),
        _doc(0.11, chunk_id="c2"),
        _doc(0.10, chunk_id="c3"),
    ]
    result = apply_rerank_gate(
        docs,
        question="bearing temperature MC-001",
        degraded=True,
        degraded_policy=DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK,
    )
    assert result.passed is False
    assert result.max_score == pytest.approx(0.12)


def test_strong_fusion_gap_passes_degraded_gate() -> None:
    docs = [
        _doc(0.45, chunk_id="c1"),
        _doc(0.18, chunk_id="c2"),
        _doc(0.12, chunk_id="c3"),
    ]
    result = apply_rerank_gate(
        docs,
        question="bearing temperature MC-001",
        degraded=True,
        degraded_policy=DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK,
    )
    assert result.passed is True


def test_abstain_policy_forces_gate_fail() -> None:
    docs = [_doc(0.40, chunk_id="c1"), _doc(0.35, chunk_id="c2")]
    result = apply_rerank_gate(
        docs,
        intent_plan=IntentRouter().route("LOTO lockout breaker MC-001"),
        degraded=True,
        degraded_policy=DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN,
    )
    assert result.passed is False
