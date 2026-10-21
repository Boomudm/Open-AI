"""Structured retrieval feature logging for offline LTR analysis (Phase 9)."""

from __future__ import annotations

from typing import Any

from spark.retrieval.intent.apply import intent_document_type_matches
from spark.retrieval.intent.router import IntentPlan
from spark.retrieval.common import log
from spark.retrieval.models import RetrievedDoc


def log_retrieval_features(
    *,
    query_id: str | None,
    candidates: list[RetrievedDoc],
    plan: IntentPlan,
    weight_version: int | str,
    factory_id: str | None = None,
    vector_count: int = 0,
    lexical_count: int = 0,
    sparse_leg_weight: float = 0.0,
    sparse_encoder_id: str | None = None,
) -> None:
    """Emit non-PII retrieval features for offline calibration / future LTR."""
    top_types: list[str] = []
    hint_matches = 0
    for doc in candidates[:10]:
        doc_type = str(doc.payload.get("document_type") or "")
        top_types.append(doc_type)
        if intent_document_type_matches(plan, doc):
            hint_matches += 1

    payload: dict[str, Any] = {
        "query_id": query_id,
        "intent": plan.intent.value,
        "classifier_confidence": plan.classifier_confidence,
        "route_source": plan.route_source,
        "clarification_suggested": plan.clarification_suggested,
        "weight_version": str(weight_version),
        "factory_id": factory_id,
        "candidate_count": len(candidates),
        "vector_count": vector_count,
        "lexical_count": lexical_count,
        "sparse_encoder_id": sparse_encoder_id or "none",
        "sparse_leg_weight": sparse_leg_weight,
        "document_type_hint": plan.document_type_hint,
        "hint_match_top10": hint_matches,
        "top_document_types": top_types[:5],
        "dense_weight": plan.dense_weight,
        "lexical_weight": plan.lexical_weight,
    }
    log.info("rag_retrieval_features", **payload)
