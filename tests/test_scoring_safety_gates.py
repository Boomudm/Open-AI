from __future__ import annotations

import pytest

from spark.retrieval.models import RAGFilter
from spark.retrieval.rerank.gates_config import load_rerank_gates_config
from spark.retrieval.scoring import (
    GateThresholds,
    _filter_machine_conflicts,
    is_loto_or_safety,
    passes_authoritative_relevance_gate,
    thresholds_for_question,
)
from spark.services.rag_service import RetrievedDoc


def test_loto_question_uses_elevated_gate() -> None:
    loto = load_rerank_gates_config().for_intent("safety_loto")
    thresholds = thresholds_for_question("LOTO procedure before servo repair")
    assert thresholds == GateThresholds(max=loto.max, avg=loto.avg)
    assert is_loto_or_safety("lockout tagout breaker")


def test_loto_low_confidence_fails_gate() -> None:
    docs = [
        RetrievedDoc(page_content="step", score=0.40, vector_score=0.40, payload={"chunk_id": "1"}),
        RetrievedDoc(page_content="step2", score=0.38, vector_score=0.38, payload={"chunk_id": "2"}),
    ]
    assert not passes_authoritative_relevance_gate(
        docs,
        question="LOTO steps for MC-001",
    )


def test_general_question_uses_default_gate() -> None:
    question = "factory shift schedule MC-001"
    thresholds = thresholds_for_question(question)
    from spark.retrieval.intent.router import IntentRouter

    plan = IntentRouter().route(question)
    expected = load_rerank_gates_config().for_intent(plan.intent.value)
    assert thresholds.max == pytest.approx(expected.max)
    assert thresholds.avg == pytest.approx(expected.avg)


def test_should_refuse_safety_bypass_and_numeric_limit_trap() -> None:
    from spark.retrieval.models import RAGFilter
    from spark.retrieval.scoring import should_refuse_rag_answer
    from spark.services.rag_service import RetrievedDoc

    assert (
        should_refuse_rag_answer(
            "ช่างขอ skip LOTO ชั่วคราวตอน hydraulic idle ได้ไหม",
            RAGFilter(machine_id="MC-002"),
            [],
        )
        == "safety_bypass_request"
    )
    assert (
        should_refuse_rag_answer(
            "Hydraulic Press MC-002 มีอาการสั่นตอนเดินเครื่อง ควรเช็คอะไร",
            RAGFilter(machine_id="MC-001"),
            [],
        )
        == "filter_machine_mismatch"
    )
    warn_only_doc = RetrievedDoc(
        page_content="WARNING: Check cooling fan if temperature exceeds 80°C.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": "1", "document_type": "machine_manual", "machine_id": "MC-001"},
    )
    assert (
        should_refuse_rag_answer(
            "MC-001 bearing housing อุณหภูมิสูงสุดที่อนุญาตเท่าไร",
            RAGFilter(machine_id="MC-001"),
            [warn_only_doc],
        )
        == "numeric_limit_ungrounded"
    )
    assert (
        should_refuse_rag_answer(
            "MC-001 bearing housing อุณหภูมิสูงสุดที่อนุญาตเท่าไร",
            RAGFilter(machine_id="MC-001"),
            [
                RetrievedDoc(
                    page_content="Maximum housing temperature must not exceed 80°C.",
                    score=0.9,
                    vector_score=0.9,
                    payload={"chunk_id": "2", "document_type": "machine_manual"},
                )
            ],
        )
        is None
    )


def test_should_refuse_unknown_machine_filter_fails_closed() -> None:
    """Adversarial regression: machine-agnostic docs match any machine_id
    filter, so scoping to a machine the factory doesn't have must refuse
    before generation instead of answering from factory-level documents."""
    from spark.retrieval.models import RAGFilter
    from spark.retrieval.scoring import should_refuse_rag_answer

    registry = {"MC-001", "MC-002"}
    assert (
        should_refuse_rag_answer(
            "MC-999 ต้องตรวจสอบอะไรบ้างก่อนใช้งาน",
            RAGFilter(factory_id="F-01", machine_id="MC-999"),
            [],
            known_factory_machines=registry,
        )
        == "unknown_machine"
    )
    # Known machine passes; empty registry (factory without machine rows)
    # must not refuse.
    assert (
        should_refuse_rag_answer(
            "MC-001 ต้องตรวจสอบอะไรบ้างก่อนใช้งาน",
            RAGFilter(factory_id="F-01", machine_id="MC-001"),
            [],
            known_factory_machines=registry,
        )
        is None
    )
    assert (
        should_refuse_rag_answer(
            "MC-999 ต้องตรวจสอบอะไรบ้างก่อนใช้งาน",
            RAGFilter(factory_id="F-01", machine_id="MC-999"),
            [],
            known_factory_machines=None,
        )
        is None
    )


def test_alpha_only_machine_id_drops_other_machine_docs() -> None:
    """`_MACHINE_ID_RE` requires a digit, so alpha-only machine_ids like
    'MC-GOLDEN-KSS'/'MC-GOLDEN-SERVO' are never extracted by it. Without a
    registry-aware fallback, asking about one machine silently returned the
    other machine's manual as a "verified" answer (found live 2026-07-11)."""
    registry = {"MC-GOLDEN-KSS", "MC-GOLDEN-SERVO"}
    docs = [
        RetrievedDoc(
            page_content="KSS wiring pinout",
            score=0.95,
            vector_score=0.95,
            payload={"machine_id": "MC-GOLDEN-KSS", "chunk_id": "1"},
        ),
    ]
    filtered = _filter_machine_conflicts(
        "servo motor MC-GOLDEN-SERVO มีสเปกกำลังไฟเท่าไหร่",
        RAGFilter(factory_id="F-GOLDEN"),
        docs,
        known_factory_machines=registry,
    )
    assert filtered == []


def test_alpha_only_machine_alias_keeps_matching_docs() -> None:
    """The same alias fallback must not drop docs that DO belong to the
    machine actually mentioned (short alias 'KSS', not the full machine_id)."""
    registry = {"MC-GOLDEN-KSS", "MC-GOLDEN-SERVO"}
    docs = [
        RetrievedDoc(
            page_content="Weight approx. 9.8 kg",
            score=0.98,
            vector_score=0.98,
            payload={"machine_id": "MC-GOLDEN-KSS", "chunk_id": "1"},
        ),
    ]
    filtered = _filter_machine_conflicts(
        "น้ำหนักของ KSS controller ประมาณกี่กิโลกรัม",
        RAGFilter(factory_id="F-GOLDEN"),
        docs,
        known_factory_machines=registry,
    )
    assert filtered == docs
