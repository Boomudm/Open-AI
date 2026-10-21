"""Regression tests for RAG-only intent routing."""

from __future__ import annotations

import pytest

from spark.services.intent_classifier import classify_intent, route_question, routing_to_intent


@pytest.mark.asyncio
async def test_document_question_with_thai_analytic_wording_is_factual() -> None:
    intent = await classify_intent(
        "ปริมาณ coolant reserve สำหรับ SPARK-HANDOVER เท่าไหร่ จากเอกสารที่อัปโหลด"
    )
    assert intent == "factual"


@pytest.mark.asyncio
async def test_document_question_with_how_much_is_factual() -> None:
    intent = await classify_intent(
        "How much coolant reserve is required according to the uploaded document?"
    )
    assert intent == "factual"


@pytest.mark.asyncio
async def test_document_type_filter_routes_to_factual() -> None:
    intent = await classify_intent(
        "แรงดันไฟฟ้าต้องอยู่ที่เท่าไหร่",
        document_type="machine_manual",
    )
    assert intent == "factual"


@pytest.mark.asyncio
async def test_analytic_wording_still_routes_to_factual_rag_only() -> None:
    intent = await classify_intent("เครื่องไหน downtime สูงสุดเดือนนี้")
    assert intent == "factual"


@pytest.mark.asyncio
async def test_aggregate_question_routes_to_rag() -> None:
    routing = route_question("MC-001 ซ่อมกี่ครั้งแล้ว")
    assert routing.route == "rag"
    assert routing_to_intent(routing) == "factual"


@pytest.mark.asyncio
async def test_followup_rag_requires_prior_message() -> None:
    routing_no_prior = route_question("แล้วเปลี่ยนยังไง")
    assert routing_no_prior.route == "rag"
    assert routing_no_prior.is_followup is False

    routing_with_prior = route_question("แล้วเปลี่ยนยังไง", has_prior_user_message=True)
    assert routing_with_prior.route == "rag"
    assert routing_with_prior.is_followup is True
    assert routing_to_intent(routing_with_prior) == "followup"
