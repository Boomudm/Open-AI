"""Answer-method routing — unified context-aware scope selection.

Covers the three regressions the unified router fixes:
  1. the chitchat detector no longer swallows real machine how-to questions;
  2. content routing defers to one context-aware judge (not blind keywords);
  3. scope is sticky across a conversation via SessionSlots.pipeline.
"""

from __future__ import annotations

import asyncio

import pytest

from spark.retrieval.enterprise_service import _is_chitchat
from spark.retrieval.models import RAGFilter
from spark.services.chat_orchestrator import ChatOrchestrator
from spark.services.session_slots import SessionSlots


def _route(orch: ChatOrchestrator, question: str, filt: RAGFilter, **kwargs):
    return asyncio.run(orch._route_question_scope(question, filt, **kwargs))


# --- 1. chitchat detector must not swallow real machine questions -----------


@pytest.mark.parametrize(
    "question",
    [
        "เครื่อง CNC ตัวนี้ใช้ยังไง",
        "ปั๊มน้ำใช้อย่างไร",
        "เครื่องนี้ทำอะไรได้บ้าง",
        "robot KUKA ใช้ยังไงครับ",
        "มอเตอร์ตัวนี้ควบคุมยังไง",
    ],
)
def test_machine_howto_is_not_chitchat(question: str) -> None:
    assert _is_chitchat(question) is False


@pytest.mark.parametrize(
    "question",
    [
        "คุณทำอะไรได้บ้าง",
        "neo ช่วยอะไรได้บ้าง",
        "ทำอะไรได้บ้างครับ",
        "สวัสดีครับ",
        "คุณชื่ออะไร",
        "ขอบคุณครับ",
    ],
)
def test_assistant_chitchat_still_detected(question: str) -> None:
    assert _is_chitchat(question) is True


def test_cnc_howto_routes_to_machinery_without_judge() -> None:
    """The added high-precision "cnc" hint keeps the common case off the LLM."""
    orch = ChatOrchestrator()
    scope, reason, answer = _route(
        orch, "เครื่อง CNC ตัวนี้ใช้ยังไง", RAGFilter(factory_id="F-01")
    )
    assert scope == "machinery"
    assert reason == "machinery_auto_keywords"
    assert answer is None


# --- 2. content routing defers to one context-aware judge -------------------


def test_both_hints_defer_to_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """When enterprise AND machine hints both fire, the judge decides — the old
    code blindly chose machinery."""
    seen: dict[str, str] = {}

    async def fake_judge(prompt, options, **kwargs):
        seen["prompt"] = prompt
        return "ENTERPRISE"

    monkeypatch.setattr("spark.services.llm_judge.judge_one_word", fake_judge)
    orch = ChatOrchestrator()
    scope, reason, _ = _route(
        orch,
        "พนักงานเดินเครื่องจักร ต้องอบรมความปลอดภัยอะไรบ้าง",
        RAGFilter(factory_id="F-01"),
    )
    assert scope == "enterprise"
    assert reason == "enterprise_auto_judge"
    assert "prompt" in seen  # judge was consulted, not short-circuited


def test_followup_gives_judge_the_prior_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """A context-light follow-up carries no keywords; the judge must see the
    prior question so it routes by conversation topic."""
    seen: dict[str, str] = {}

    async def fake_judge(prompt, options, **kwargs):
        seen["prompt"] = prompt
        return "ENTERPRISE"

    monkeypatch.setattr("spark.services.llm_judge.judge_one_word", fake_judge)
    orch = ChatOrchestrator()
    scope, _reason, _ = _route(
        orch,
        "แล้วลากิจล่ะ",
        RAGFilter(factory_id="F-01"),
        is_followup=True,
        prior_user_question="ลาป่วยได้กี่วัน",
        prior_scope="enterprise",
    )
    assert scope == "enterprise"
    assert "ลาป่วยได้กี่วัน" in seen["prompt"]


def test_non_followup_hides_prior_question_from_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    async def fake_judge(prompt, options, **kwargs):
        seen["prompt"] = prompt
        return "MACHINERY"

    monkeypatch.setattr("spark.services.llm_judge.judge_one_word", fake_judge)
    orch = ChatOrchestrator()
    _route(
        orch,
        "อันนี้เท่าไหร่",
        RAGFilter(factory_id="F-01"),
        is_followup=False,
        prior_user_question="ลาป่วยได้กี่วัน",
        prior_scope="enterprise",
    )
    assert "ลาป่วยได้กี่วัน" not in seen["prompt"]


# --- 3. scope stickiness / fail-safe ---------------------------------------


def test_judge_failure_inherits_prior_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_judge(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("spark.services.llm_judge.judge_one_word", fake_judge)
    orch = ChatOrchestrator()
    scope, reason, _ = _route(
        orch,
        "แล้วอันนี้ล่ะ",
        RAGFilter(factory_id="F-01"),
        is_followup=True,
        prior_user_question="ประวัติซ่อมเครื่อง",
        prior_scope="machinery",
    )
    assert scope == "machinery"
    assert reason == "sticky_default:machinery"


def test_judge_none_no_prior_defaults_machinery(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_judge(*args, **kwargs):
        return None

    monkeypatch.setattr("spark.services.llm_judge.judge_one_word", fake_judge)
    orch = ChatOrchestrator()
    scope, reason, _ = _route(orch, "อันนี้เท่าไหร่", RAGFilter(factory_id="F-01"))
    assert scope == "machinery"
    assert reason == "machinery_default"


# --- SessionSlots.pipeline persistence -------------------------------------


def test_apply_turn_persists_content_scope() -> None:
    slots = SessionSlots().apply_turn(
        question="ลาป่วยกี่วัน",
        rf=RAGFilter(factory_id="F-01"),
        chunk_ids=[],
        pipeline="enterprise",
    )
    assert slots.pipeline == "enterprise"
    ctx = slots.to_context_dict()
    assert ctx.get("pipeline") == "enterprise"
    assert SessionSlots.from_context(ctx).pipeline == "enterprise"


def test_apply_turn_chitchat_turn_carries_scope_forward() -> None:
    slots = SessionSlots(pipeline="machinery").apply_turn(
        question="ขอบคุณครับ",
        rf=RAGFilter(factory_id="F-01"),
        chunk_ids=[],
        pipeline=None,
    )
    assert slots.pipeline == "machinery"


def test_apply_turn_switches_scope_on_new_content() -> None:
    slots = SessionSlots(pipeline="machinery").apply_turn(
        question="ลาป่วยกี่วัน",
        rf=RAGFilter(factory_id="F-01"),
        chunk_ids=[],
        pipeline="enterprise",
    )
    assert slots.pipeline == "enterprise"
