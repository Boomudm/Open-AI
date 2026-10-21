"""Phase 9 — classifier abstention routes to UNKNOWN."""

from __future__ import annotations

from spark.retrieval.intent.classifier import IntentClassifier
from spark.retrieval.intent.router import IntentRouter, QueryIntent


def test_low_confidence_routes_to_unknown() -> None:
    strict = IntentClassifier.from_json()
    strict = IntentClassifier(
        abstain_threshold=0.99,
        centroids=strict.centroids,
        embed_fn=strict.embed_fn,
    )
    router = IntentRouter(classifier=strict)
    plan = router.route("z")
    assert plan.intent == QueryIntent.UNKNOWN
    assert plan.clarification_suggested is True
    assert plan.route_source == "classifier_abstain"
    assert plan.classifier_confidence is not None


def test_confident_procedure_routes_via_classifier() -> None:
    router = IntentRouter()
    plan = router.route("how to replace the cooling fan belt step by step")
    assert plan.intent == QueryIntent.PROCEDURE
    assert plan.route_source == "classifier"
    assert plan.classifier_confidence is not None
