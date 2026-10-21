"""Phase 9 safety intent classifier tests."""

from __future__ import annotations

from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent


def test_paraphrased_loto_detected_without_eval_baseline_match() -> None:
    intent = detect_safety_intent("ก่อนซ่อมเครื่องต้อง lock out tag out breaker ยังไง")
    assert intent.kind == SafetyIntentKind.LOTO


def test_emergency_override_detected() -> None:
    intent = detect_safety_intent("Can we skip lockout temporarily for a quick hydraulic check?")
    assert intent.kind == SafetyIntentKind.EMERGENCY_OVERRIDE


def test_general_question_has_no_safety_intent() -> None:
    intent = detect_safety_intent("bearing temperature MC-001 normal range")
    assert intent.kind == SafetyIntentKind.NONE
