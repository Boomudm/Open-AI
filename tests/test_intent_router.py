"""Intent router tests (Phase 7)."""

from __future__ import annotations

from spark.retrieval.intent.router import IntentRouter, QueryIntent


def test_part_lookup_high_lexical_weight() -> None:
    plan = IntentRouter().route("Need SKF-6205 bearing replacement part")
    assert plan.intent == QueryIntent.PART_LOOKUP
    assert plan.lexical_weight > plan.dense_weight
    assert plan.lexical_weight >= 0.7


def test_alarm_diagnostic_elevates_dense_weight() -> None:
    plan = IntentRouter().route("Alarm E-204 servo motor overheat")
    assert plan.intent == QueryIntent.ALARM_DIAGNOSTIC
    assert plan.dense_weight >= 0.6


def test_safety_loto_intent() -> None:
    plan = IntentRouter().route("ขั้นตอน LOTO ก่อนซ่อม")
    assert plan.intent == QueryIntent.SAFETY_LOTO
    assert plan.min_rerank_score is not None


def test_io_mapping_intent_from_plc_tag() -> None:
    plan = IntentRouter().route("RES0.BELT_CALIB_SENSOR เชื่อมกับอะไร")
    assert plan.intent == QueryIntent.IO_MAPPING
    assert plan.document_type_hint == "io_mapping"
    assert plan.lexical_weight > plan.dense_weight
    assert plan.strict_document_type_filter is True


def test_io_mapping_intent_takes_priority_over_part_lookup() -> None:
    # Dotted PLC paths must not be swallowed by the part-number regex cascade.
    plan = IntentRouter().route("RES0.SERVO_BELT.Destination คืออะไร")
    assert plan.intent == QueryIntent.IO_MAPPING
