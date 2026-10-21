from __future__ import annotations

from spark.retrieval.safety.fallback_ladder import (
    FallbackContext,
    build_fallback_levels,
    can_broaden_machine_scope,
    question_has_machine_anchor_tokens,
)
from spark.retrieval.models import RAGFilter


def test_machine_anchor_tokens_block_broadening_even_with_flag() -> None:
    ctx = FallbackContext(
        question="Servo MC-001 ร้อน",
        rf=RAGFilter(factory_id="F-01"),
        allow_scope_broadening=True,
    )
    assert question_has_machine_anchor_tokens(ctx.question)
    assert can_broaden_machine_scope(ctx) is False


def test_scope_broadening_requires_explicit_flag() -> None:
    ctx = FallbackContext(
        question="bearing temperature",
        rf=RAGFilter(factory_id="F-01", machine_id="MC-001"),
        allow_scope_broadening=False,
    )
    levels = build_fallback_levels(ctx)
    assert all(level < 3 for level, _ in levels)


def test_scope_broadening_adds_levels_when_allowed() -> None:
    ctx = FallbackContext(
        question="bearing temperature",
        rf=RAGFilter(factory_id="F-01", machine_id="MC-001"),
        allow_scope_broadening=True,
    )
    levels = build_fallback_levels(ctx)
    assert {level for level, _ in levels} >= {0, 3}
    assert 4 not in {level for level, _ in levels}
