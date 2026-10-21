"""Tests for chat filter merge defaults (Phase 10)."""

from __future__ import annotations

import asyncio

from spark.retrieval.models import RAGFilter
from spark.services.chat_orchestrator import ChatOrchestrator
from spark.schemas.rag import RAGFilterModel


def test_merge_filter_no_revision_hiding_by_default() -> None:
    """Product decision 2026-07: no automatic latest-revision filtering — a
    manual uploaded without revision metadata must never be hidden from
    answers. Employees manage outdated documents via the frontend."""
    orchestrator = ChatOrchestrator()
    rf = orchestrator._merge_filter(
        {"factory_id": "F-01"},
        RAGFilterModel(document_type="machine_manual"),
    )
    assert rf.latest_revision_only is False


def test_merge_filter_explicit_latest_revision_still_works() -> None:
    orchestrator = ChatOrchestrator()
    rf = orchestrator._merge_filter(
        {"factory_id": "F-01"},
        RAGFilterModel(document_type="machine_manual", latest_revision_only=True),
    )
    assert rf.latest_revision_only is True


def test_merge_filter_uses_confirmed_machine_id() -> None:
    orchestrator = ChatOrchestrator()
    rf = orchestrator._merge_filter(
        {"confirmed_machine_id": "MC-001", "machine_id": "MC-002"},
        None,
    )
    assert rf.machine_id == "MC-001"


def test_merge_filter_carries_drawing_no_from_request() -> None:
    """Regression: RAGFilter gained drawing_no but SessionSlots didn't — every
    chat ask that merged filters raised AttributeError (500) until the slot
    model learned the field."""
    orchestrator = ChatOrchestrator()
    rf = orchestrator._merge_filter(
        {"factory_id": "F-01"},
        RAGFilterModel(drawing_no="EE-07"),
    )
    assert rf.drawing_no == "EE-07"


def test_merge_filter_drawing_no_defaults_none() -> None:
    orchestrator = ChatOrchestrator()
    rf = orchestrator._merge_filter({"factory_id": "F-01"}, None)
    assert rf.drawing_no is None


def test_hr_question_routes_enterprise_without_frontend_toggle() -> None:
    orchestrator = ChatOrchestrator()
    route, reason = asyncio.run(
        orchestrator._should_route_enterprise(
            "ลาป่วยได้กี่วัน และต้องแจ้งฝ่ายบุคคลไหม",
            RAGFilter(factory_id="F-01"),
        )
    )
    assert route is True
    assert reason == "enterprise_auto_keywords"


def test_greeting_routes_to_chitchat_before_hr_or_machine() -> None:
    orchestrator = ChatOrchestrator()
    scope, reason, answer = asyncio.run(
        orchestrator._route_question_scope(
            "สวัสดีครับ",
            RAGFilter(factory_id="F-01"),
        )
    )
    assert scope == "chitchat"
    assert reason == "skip_chitchat"
    assert answer


def test_chitchat_is_not_enterprise_pipeline() -> None:
    orchestrator = ChatOrchestrator()
    route, reason = asyncio.run(
        orchestrator._should_route_enterprise(
            "สวัสดีครับ",
            RAGFilter(factory_id="F-01"),
        )
    )
    assert route is False
    assert reason == "skip_chitchat"


def test_smalltalk_routes_to_chitchat_without_judge() -> None:
    orchestrator = ChatOrchestrator()
    scope, reason, answer = asyncio.run(
        orchestrator._route_question_scope(
            "วันนี้เป็นยังไง",
            RAGFilter(factory_id="F-01"),
        )
    )
    assert scope == "chitchat"
    assert reason == "skip_chitchat"
    assert answer


def test_machine_question_defaults_to_machinery_without_machine_scope() -> None:
    orchestrator = ChatOrchestrator()
    route, reason = asyncio.run(
        orchestrator._should_route_enterprise(
            "KSS jog velocity limit ตั้งไว้เท่าไหร่",
            RAGFilter(factory_id="F-01"),
        )
    )
    assert route is False
    assert reason == "machinery_auto_keywords"
