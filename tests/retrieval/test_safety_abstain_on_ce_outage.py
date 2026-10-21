"""Phase 7 — safety intents abstain or extractive-only when CE rerank is down."""

from __future__ import annotations

from spark.retrieval.degraded_policy import apply_degraded_rerank
from spark.retrieval.degraded_types import DegradedRetrievalPolicy
from spark.retrieval.intent.router import QueryIntent
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent


def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="LOTO lockout procedure step 1",
        score=score,
        vector_score=score,
        fusion_score=score,
        payload={"chunk_id": "s1", "document_type": "sop"},
    )


def test_safety_weak_fusion_abstains() -> None:
    docs = [_doc(0.10), _doc(0.09)]
    _, policy = apply_degraded_rerank(
        docs,
        intent=QueryIntent.SAFETY_LOTO,
        safety_intent_kind=SafetyIntentKind.LOTO.value,
        ce_available=False,
    )
    assert policy == DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN


def test_safety_strong_fusion_extractive_only() -> None:
    docs = [_doc(0.40), _doc(0.15)]
    _, policy = apply_degraded_rerank(
        docs,
        intent=QueryIntent.SAFETY_LOTO,
        safety_intent_kind=SafetyIntentKind.LOTO.value,
        ce_available=False,
    )
    assert policy == DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY


def test_loto_question_detected_for_safety_path() -> None:
    intent = detect_safety_intent("LOTO lockout breaker MC-001 before service")
    assert intent.kind == SafetyIntentKind.LOTO
