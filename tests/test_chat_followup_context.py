"""Tests for legacy contextualize helper (superseded by query rewrite in Phase 10)."""

from __future__ import annotations

from types import SimpleNamespace

from spark.services.chat_orchestrator import ChatOrchestrator
from spark.services.intent_classifier import QuestionRouting
from spark.retrieval.preprocess.rewrite import rules_rewrite_for_retrieval
from spark.services.rag_service import RAGFilter


def test_followup_rules_rewrite_includes_previous_question_and_machine() -> None:
    prior_messages = [
        SimpleNamespace(
            role="user",
            content="Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
            sources=None,
        ),
        SimpleNamespace(
            role="assistant",
            content="ให้ตรวจพัดลมระบายความร้อน",
            sources=[
                {
                    "source_file": "manual.pdf",
                    "page": 13,
                    "document_type": "machine_manual",
                }
            ],
        ),
    ]

    rewritten, meta = rules_rewrite_for_retrieval(
        "แล้วต้องหยุดเครื่องไหม",
        [("human", prior_messages[0].content), ("ai", prior_messages[1].content)],
        {"machine_id": "MC-001"},
        has_prior_user_message=True,
    )

    assert meta["follow_up"] is True
    assert "MC-001" in rewritten
    assert "ร้อนผิดปกติ" in rewritten
    assert "แล้วต้องหยุดเครื่องไหม" in rewritten


def test_non_followup_question_is_not_rewritten() -> None:
    rewritten, meta = rules_rewrite_for_retrieval(
        "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
        [],
        {"machine_id": "MC-001"},
        has_prior_user_message=False,
    )

    assert meta["follow_up"] is False
    assert rewritten == "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร"


def test_legacy_contextualize_still_available() -> None:
    orchestrator = ChatOrchestrator()
    effective = orchestrator._contextualize_question(
        "แล้วต้องหยุดเครื่องไหม",
        QuestionRouting(route="rag", is_followup=True, reason="keyword:followup"),
        RAGFilter(machine_id="MC-001"),
        [],
    )
    assert "คำถามต่อเนื่อง" in effective
