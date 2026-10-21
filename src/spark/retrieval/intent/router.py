"""Intent-aware retrieval routing — regex cascade + embedding classifier (Phase 9)."""

from __future__ import annotations

from spark.retrieval.constants import MIN_RERANK_SCORE

from . import features
from .types import IntentPlan, QueryIntent
from .weights import IntentWeightSpec, load_intent_weights_config


def _plan_from_spec(
    intent: QueryIntent,
    spec: IntentWeightSpec,
    *,
    version: int,
    classifier_confidence: float | None = None,
    route_source: str = "rules",
    clarification_suggested: bool = False,
) -> IntentPlan:
    min_score = spec.min_rerank_score
    if min_score is not None and intent == QueryIntent.SAFETY_LOTO:
        min_score = max(float(MIN_RERANK_SCORE), float(min_score))
    return IntentPlan(
        intent=intent,
        dense_weight=spec.dense_weight,
        lexical_weight=spec.lexical_weight,
        document_type_hint=spec.document_type_hint,
        min_rerank_score=min_score,
        strict_document_type_filter=spec.strict_document_type_filter,
        weight_version=version,
        classifier_confidence=classifier_confidence,
        route_source=route_source,
        clarification_suggested=clarification_suggested,
    )


class IntentRouter:
    """Two-stage router: high-precision regex → embedding classifier with abstention."""

    def __init__(
        self,
        *,
        weights_path: str | None = None,
        classifier=None,
    ) -> None:
        self._weights_path = weights_path
        self._classifier_override = classifier

    def _config(self):
        return load_intent_weights_config(self._weights_path)

    def _get_classifier(self):
        if self._classifier_override is not None:
            return self._classifier_override
        from .classifier import get_intent_classifier

        return get_intent_classifier()

    async def route_async(self, question: str) -> IntentPlan:
        """route() plus an LLM judge lane for questions no regex lane claims.

        The regex lanes (LOTO, PLC tag, part, alarm) are exact signals and
        stay first. The centroid classifier that used to decide everything
        else mislabeled ordinary manual questions (e.g. a jog-velocity spec
        question as "procedure"), dragging them under the wrong rerank gates.
        The judge fails safe: None -> same classifier path as before.
        """
        cfg = self._config()
        q = (question or "").strip()
        plan = self.route(q)
        if plan.route_source.startswith("regex") or not q:
            return plan
        try:
            from spark.services.llm_judge import judge_one_word

            verdict = await judge_one_word(
                (
                    "จัดประเภทคำถามของช่างซ่อมบำรุงนี้\n"
                    f"คำถาม: {q[:300]}\n"
                    "PROCEDURE = ถามขั้นตอนการทำงาน/วิธีทำทีละขั้น\n"
                    "ALARM = ถามความหมาย/วิธีแก้รหัส alarm หรือ error\n"
                    "PART = ถามหารุ่น/รหัสอะไหล่\n"
                    "GENERAL = ถามข้อมูล สเปค ค่าตัวเลข หรืออื่นๆ"
                ),
                ["PROCEDURE", "ALARM", "PART", "GENERAL"],
            )
        except Exception:  # noqa: BLE001
            verdict = None
        if verdict is None:
            return plan
        mapping = {
            "PROCEDURE": QueryIntent.PROCEDURE,
            "ALARM": QueryIntent.ALARM_DIAGNOSTIC,
            "PART": QueryIntent.PART_LOOKUP,
            "GENERAL": QueryIntent.GENERAL,
        }
        intent = mapping[verdict]
        return _plan_from_spec(
            intent,
            cfg.for_intent(intent if intent != QueryIntent.GENERAL else "general"),
            version=cfg.version,
            route_source="llm_judge",
        )

    def route(self, question: str) -> IntentPlan:
        cfg = self._config()
        q = (question or "").strip()
        if not q:
            return _plan_from_spec(QueryIntent.GENERAL, cfg.for_intent("general"), version=cfg.version)

        if features.has_loto_terms(q):
            return _plan_from_spec(
                QueryIntent.SAFETY_LOTO,
                cfg.for_intent(QueryIntent.SAFETY_LOTO),
                version=cfg.version,
                route_source="regex_loto",
            )

        if features.has_io_mapping_terms(q):
            return _plan_from_spec(
                QueryIntent.IO_MAPPING,
                cfg.for_intent(QueryIntent.IO_MAPPING),
                version=cfg.version,
                route_source="regex_io_mapping",
            )

        if features.has_drawing_terms(q):
            return _plan_from_spec(
                QueryIntent.DRAWING,
                cfg.for_intent(QueryIntent.DRAWING),
                version=cfg.version,
                route_source="regex_drawing",
            )

        if features.has_wiring_connectivity_terms(q):
            # Connectivity phrasing without the word "diagram" ("M18 ต่อกับอะไร",
            # "ถ้า K1 เสีย กระทบอะไร"). Soft variant of the drawing route: the
            # lexical-heavy weights and drawing rank-prior apply, but no strict
            # document filter — a machine manual may legitimately carry the
            # answer, and drawing_connectivity must never hide it.
            return _plan_from_spec(
                QueryIntent.DRAWING,
                cfg.for_intent("drawing_connectivity"),
                version=cfg.version,
                route_source="regex_drawing_connectivity",
            )

        if features.has_part_number(q):
            return _plan_from_spec(
                QueryIntent.PART_LOOKUP,
                cfg.for_intent(QueryIntent.PART_LOOKUP),
                version=cfg.version,
                route_source="regex_part",
            )

        if features.has_alarm_code(q):
            return _plan_from_spec(
                QueryIntent.ALARM_DIAGNOSTIC,
                cfg.for_intent(QueryIntent.ALARM_DIAGNOSTIC),
                version=cfg.version,
                route_source="regex_alarm",
            )

        if features.has_manual_lookup_terms(q):
            return _plan_from_spec(
                QueryIntent.GENERAL,
                cfg.for_intent(QueryIntent.GENERAL),
                version=cfg.version,
                route_source="regex_manual_lookup",
            )

        from .classifier import IntentClassifier

        classifier = self._get_classifier()
        if isinstance(classifier, IntentClassifier) and classifier.abstain_threshold != cfg.abstain_threshold:
            classifier = IntentClassifier(
                abstain_threshold=cfg.abstain_threshold,
                centroids=classifier.centroids,
                embed_fn=classifier.embed_fn,
            )
        prediction = classifier.predict(q)
        if prediction.intent == QueryIntent.UNKNOWN:
            return _plan_from_spec(
                QueryIntent.UNKNOWN,
                cfg.for_intent("general"),
                version=cfg.version,
                classifier_confidence=prediction.confidence,
                route_source="classifier_abstain",
                clarification_suggested=True,
            )

        return _plan_from_spec(
            prediction.intent,
            cfg.for_intent(prediction.intent),
            version=cfg.version,
            classifier_confidence=prediction.confidence,
            route_source="classifier",
        )


# Backward-compatible re-exports
__all__ = ["IntentPlan", "IntentRouter", "QueryIntent", "_plan_from_spec"]
