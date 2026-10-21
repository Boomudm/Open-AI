"""Apply intent plans to retrieval filters and candidate rank priors (Phase 9)."""

from __future__ import annotations

from dataclasses import replace

from spark.retrieval.intent.types import IntentPlan, QueryIntent
from spark.retrieval.models import RAGFilter, RetrievedDoc


def apply_intent_to_filter(plan: IntentPlan, rf: RAGFilter) -> RAGFilter:
    """Apply document_type hint as filter (safety) or leave filter open for rank-prior intents."""
    if not plan.document_type_hint or rf.document_type:
        return rf
    if plan.strict_document_type_filter or plan.intent == QueryIntent.SAFETY_LOTO:
        return replace(rf, document_type=plan.document_type_hint)
    return rf


def intent_document_type_matches(plan: IntentPlan, doc: RetrievedDoc) -> bool:
    if not plan.document_type_hint:
        return False
    doc_type = str(doc.payload.get("document_type") or "").strip().lower()
    hint = plan.document_type_hint.strip().lower()
    return doc_type == hint


def apply_intent_boosts(plan: IntentPlan, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """Promote matching document_type within top-5 fusion — no score inflation."""
    if not plan.document_type_hint or not docs:
        return docs
    if plan.intent == QueryIntent.UNKNOWN:
        return docs

    top5 = docs[:5]
    rest = docs[5:]
    match_idx = None
    for idx, doc in enumerate(top5):
        if intent_document_type_matches(plan, doc):
            match_idx = idx
            break
    if match_idx is None or match_idx == 0:
        return docs
    promoted = top5[match_idx]
    reordered = [promoted] + top5[:match_idx] + top5[match_idx + 1 :]
    return reordered + rest
