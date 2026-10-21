"""Tests for conversational query rewrite and follow-up detection (Phase 10)."""

from __future__ import annotations

import pytest

from spark.retrieval.preprocess.follow_up import is_follow_up_question
from spark.retrieval.preprocess.rewrite import rules_rewrite_for_retrieval


def test_follow_up_detects_thai_continuation() -> None:
    assert is_follow_up_question(
        "แล้วต้องหยุดเครื่องไหม",
        [("human", "Servo MC-001 ร้อนผิดปกติ")],
        has_prior_user_message=True,
    )


def test_standalone_question_with_machine_not_follow_up() -> None:
    assert not is_follow_up_question(
        "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
        [],
        has_prior_user_message=False,
    )


def test_rules_rewrite_includes_session_machine_for_follow_up() -> None:
    rewritten, meta = rules_rewrite_for_retrieval(
        "แล้วต้องหยุดเครื่องไหม",
        [("human", "Servo MC-001 ร้อนผิดปกติ ต้องทำอะไร")],
        {"confirmed_machine_id": "MC-001"},
        has_prior_user_message=True,
    )
    assert meta["follow_up"] is True
    assert "MC-001" in rewritten or "machine_id MC-001" in rewritten
    assert "ร้อนผิดปกติ" in rewritten


def test_rules_rewrite_skips_prior_for_new_topic() -> None:
    rewritten, meta = rules_rewrite_for_retrieval(
        "Servo Motor MC-002 มีเสียงดังผิดปกติ",
        [("human", "Servo MC-001 ร้อนผิดปกติ")],
        {"machine_id": "MC-001"},
        has_prior_user_message=True,
    )
    assert meta["follow_up"] is False
    assert "MC-002" in rewritten
    assert "ร้อนผิดปกติ" not in rewritten


@pytest.mark.asyncio
async def test_multiturn_turn2_retrieves_with_machine_from_session() -> None:
    from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval

    turn1 = "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร"
    turn2 = "แล้วต้องหยุดเครื่องไหม"
    history = [("human", turn1), ("ai", "ตรวจพัดลมระบายความร้อน")]
    rewritten, meta = await rewrite_for_retrieval(
        turn2,
        history,
        {"confirmed_machine_id": "MC-001", "machine_id": "MC-001"},
        llm_rewrite_enabled=False,
        has_prior_user_message=True,
    )
    assert "MC-001" in rewritten
    assert turn1.split()[2] in rewritten or "MC-001" in rewritten
    assert meta["strategy"] == "rules"


def test_follow_up_skips_turns_answered_with_no_data() -> None:
    # 17 Jul QA: the merge glued the two most-recent turns (both answered
    # no-data) and dropped the alarm turn the user was following up on.
    history = [
        ("user", "มอเตอร์ SV-01 ขึ้น Alarm 26h หมายถึงอะไร ต้องแก้ไขยังไง"),
        ("assistant", "## Alarm 26h — Motor Overheat รีเซ็ตด้วย ALM-RST [chunk_id:x]"),
        ("user", "ในตู้ควบคุม MAIN เบรกเกอร์หลักขนาดกี่แอมป์"),
        ("assistant", "จากข้อมูลในเอกสารที่ให้มา ไม่พบข้อมูลเกี่ยวกับเบรกเกอร์หลัก"),
        ("user", "ถ้าเบรกเกอร์ QM1 ในตู้ MAIN trip ไฟจะดับที่อุปกรณ์ไหนบ้าง"),
        ("assistant", "**ไม่พบข้อมูลเกี่ยวกับเบรกเกอร์ QM1** กรุณาติดต่อผู้ดูแลเอกสาร"),
    ]
    rewritten, meta = rules_rewrite_for_retrieval(
        "แล้วถ้ารีเซ็ต alarm นั้นแล้วยังไม่หาย ต้องทำยังไงต่อ",
        history,
        {},
        has_prior_user_message=True,
    )
    assert meta["follow_up"] is True
    assert "26h" in rewritten
    assert "QM1" not in rewritten
    assert "เบรกเกอร์หลัก" not in rewritten


def test_follow_up_prefers_topic_anchor_over_recency() -> None:
    history = [
        ("user", "Alarm 26h ของ SV-01 แก้ยังไง"),
        ("assistant", "รีเซ็ตผ่าน ALM-RST input [chunk_id:a]"),
        ("user", "KUKA KR C5 ติดตั้งในแร็คยังไง"),
        ("assistant", "ยึดด้วยสกรู TORX 4 ตัว [chunk_id:b]"),
    ]
    rewritten, _meta = rules_rewrite_for_retrieval(
        "แล้ว alarm นั้นเกิดจากอะไร",
        history,
        {},
        has_prior_user_message=True,
    )
    assert "26h" in rewritten


def test_follow_up_merge_never_cuts_mid_word() -> None:
    long_turn = ("ถ้าเบรกเกอร์ QM1 ในตู้ MAIN trip " + "ไฟจะดับที่อุปกรณ์ไหนบ้าง " * 30).strip()
    history = [
        ("user", long_turn),
        ("assistant", "คำตอบยาวๆ อ้าง [chunk_id:a]"),
    ]
    rewritten, _meta = rules_rewrite_for_retrieval(
        "แล้ว QM1 ต่อกับเฟสไหน",
        history,
        {},
        has_prior_user_message=True,
    )
    # The merged prior turn is budget-cut at whitespace, never mid-word.
    merged_head = rewritten.rsplit("แล้ว QM1", 1)[0].strip()
    assert merged_head.endswith("ไหนบ้าง") or merged_head.endswith("trip")
    # And the CURRENT question survives whole — the cap must amputate priors,
    # never the question the user just asked.
    assert rewritten.endswith("แล้ว QM1 ต่อกับเฟสไหน")
