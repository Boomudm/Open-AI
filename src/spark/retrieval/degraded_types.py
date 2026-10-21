"""Shared degraded rerank types — no rerank/safety package imports (Phase 7)."""

from __future__ import annotations

from enum import Enum

from spark.retrieval.models import RetrievedDoc


class DegradedRetrievalPolicy(str, Enum):
    CE_ACTIVE = "ce_active"
    CE_TIMEOUT_ABSTAIN = "ce_timeout_abstain"
    CE_TIMEOUT_EXTRACTIVE_ONLY = "ce_timeout_extractive_only"
    CE_TIMEOUT_FUSION_RANK = "ce_timeout_fusion_rank"


def raw_fusion_score(doc: RetrievedDoc) -> float:
    if doc.fusion_score is not None:
        return float(doc.fusion_score)
    return float(doc.score)


def is_safety_degraded_policy(policy: DegradedRetrievalPolicy) -> bool:
    return policy in {
        DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN,
        DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY,
    }
