"""Degraded rerank policy when cross-encoder is unavailable (Phase 7)."""

from __future__ import annotations

from spark.retrieval.degraded_floors_config import load_degraded_fusion_floors
from spark.retrieval.degraded_types import DegradedRetrievalPolicy, raw_fusion_score
from spark.retrieval.intent.router import QueryIntent
from spark.retrieval.models import RetrievedDoc


def apply_degraded_rerank(
    docs: list[RetrievedDoc],
    *,
    intent: QueryIntent,
    safety_intent_kind: str,
    ce_available: bool,
) -> tuple[list[RetrievedDoc], DegradedRetrievalPolicy]:
    """Order by raw fusion scores — never min-max calibrate to pass gates."""
    if ce_available:
        return docs, DegradedRetrievalPolicy.CE_ACTIVE
    if not docs:
        return [], DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK

    from spark.retrieval.safety.safety_intent import SafetyIntentKind

    ordered = sorted(docs, key=raw_fusion_score, reverse=True)
    top_raw = raw_fusion_score(ordered[0])
    floors = load_degraded_fusion_floors()

    try:
        safety_kind = SafetyIntentKind(safety_intent_kind)
    except ValueError:
        safety_kind = SafetyIntentKind.NONE

    if safety_kind != SafetyIntentKind.NONE:
        if top_raw < floors.safety_abstain_raw_fusion:
            return ordered, DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN
        return ordered, DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY

    return ordered, DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK
