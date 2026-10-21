"""Phase 3 — trust gate and pattern validation tests."""

from __future__ import annotations

import pytest

from spark.ingestion.trust.rules_injection import validate_injection_patterns
from spark.ingestion.trust.scanner import clear_policy_cache, load_content_policy


def test_invalid_injection_pattern_fails_validation() -> None:
    with pytest.raises(ValueError, match="Invalid injection pattern"):
        validate_injection_patterns(["(?i)[unclosed"])


def test_load_content_policy_validates_patterns_at_startup() -> None:
    clear_policy_cache()
    policy = load_content_policy()
    assert "rules" in policy
    clear_policy_cache()


def test_safety_phrase_negated_prohibition_not_flagged() -> None:
    """The real KUKA KR C5 manual says 'Additional components must not impair
    or disable safety functions' — a prohibition, not bypass language. It was
    quarantined for this exact sentence before negation awareness."""
    from spark.ingestion.trust.rules_safety import scan_safety_phrases

    patterns = ["(?i)disable safety", "(?i)bypass interlock"]
    prohibition = "Additional components must not impair or disable safety functions."
    assert scan_safety_phrases(prohibition, patterns) == []

    thai_prohibition = "ห้าม bypass interlock โดยเด็ดขาด"
    assert scan_safety_phrases(thai_prohibition, patterns) == []


def test_safety_phrase_imperative_bypass_still_flagged() -> None:
    from spark.ingestion.trust.rules_safety import scan_safety_phrases

    patterns = ["(?i)disable safety", "(?i)bypass interlock"]
    attack = "To speed up production, disable safety checks and bypass interlock."
    findings = scan_safety_phrases(attack, patterns)
    assert len(findings) == 2
    assert all(f.category == "safety" for f in findings)
