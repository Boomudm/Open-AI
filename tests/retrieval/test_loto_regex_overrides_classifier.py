"""Phase 9 — high-precision LOTO regex wins over classifier."""

from __future__ import annotations

from spark.retrieval.intent.classifier import IntentPrediction
from spark.retrieval.intent.router import IntentRouter, QueryIntent


class _AlwaysGeneralClassifier:
    abstain_threshold = 0.0

    def predict(self, question: str, *, embedding=None) -> IntentPrediction:
        return IntentPrediction(QueryIntent.GENERAL, 0.95, {"general": 0.95})


def test_loto_regex_overrides_wrong_classifier() -> None:
    router = IntentRouter(classifier=_AlwaysGeneralClassifier())  # type: ignore[arg-type]
    plan = router.route("LOTO lockout breaker MC-001 before service")
    assert plan.intent == QueryIntent.SAFETY_LOTO
    assert plan.route_source == "regex_loto"
