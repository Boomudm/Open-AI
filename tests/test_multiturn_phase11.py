"""Phase 11 — multi-turn session, revision, and query rewrite."""

from __future__ import annotations

import uuid

import pytest

from spark.retrieval.preprocess.follow_up import is_follow_up_question
from spark.retrieval.preprocess.follow_up_boost import boost_follow_up_chunks
from spark.retrieval.preprocess.rewrite import rules_rewrite_for_retrieval
from spark.services.document_revision import parse_revision
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.retrieval_snapshot import build_retrieval_snapshot
from spark.services.rag_service import RAGService
from spark.services.session_slots import (
    SessionSlots,
    extract_revision_from_question,
    merge_session_slots,
)


def _doc(
    text: str,
    *,
    chunk_id: str | None = None,
    revision: str | None = None,
    score: float = 0.5,
) -> RetrievedDoc:
    payload: dict = {
        "chunk_id": chunk_id or str(uuid.uuid4()),
        "doc_id": str(uuid.uuid4()),
        "revision": revision,
    }
    if revision:
        payload["revision_sort_key"] = parse_revision(revision)[0]
    return RetrievedDoc(
        page_content=text,
        score=score,
        vector_score=score,
        payload=payload,
        fusion_score=score,
    )


def test_locked_machine_scope_clarify_for_other_machine_follow_up() -> None:
    rewritten, meta = rules_rewrite_for_retrieval(
        "แล้วเครื่องอื่นล่ะ",
        [("human", "Servo MC-001 ร้อนผิดปกติ")],
        SessionSlots(
            machine_id="MC-001",
            confirmed_machine_id="MC-001",
            locked_fields=["machine_id"],
        ),
        has_prior_user_message=True,
    )
    assert meta["scope_clarify"] is True
    assert meta["follow_up"] is True
    assert "machine_id MC-001" not in rewritten


def test_revision_slot_extracted_from_question() -> None:
    assert extract_revision_from_question("ขอ manual rev C ของ MC-001") == "Rev C"


def test_revision_filter_keeps_exact_manual_version() -> None:
    svc = RAGService()
    doc_id = str(uuid.uuid4())
    rev_b = _doc("manual B", revision="Rev B", score=0.7)
    rev_b.payload["doc_id"] = doc_id
    rev_c = _doc("manual C", revision="Rev C", score=0.6)
    rev_c.payload["doc_id"] = doc_id
    filtered = svc._filter_exact_revision([rev_b, rev_c], "Rev C")
    assert len(filtered) == 1
    assert filtered[0].payload["revision"] == "Rev C"


def test_rev_c_sorts_above_rev_b() -> None:
    b_key, _ = parse_revision("Rev B")
    c_key, _ = parse_revision("Rev C")
    assert c_key > b_key


def test_follow_up_boost_promotes_prior_chunk() -> None:
    prior_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    prior = _doc("prior chunk", chunk_id=prior_id, score=0.55)
    other = _doc("other chunk", chunk_id=other_id, score=0.60)
    boosted = boost_follow_up_chunks(
        [other, prior],
        chunk_ids=[prior_id],
        follow_up=True,
        question="แล้วต้องทำอะไรต่อ",
    )
    assert boosted[0].payload["chunk_id"] == prior_id
    assert boosted[0].score > prior.score


def test_session_slots_merge_respects_locked_machine() -> None:
    slots, rf = merge_session_slots(
        {"machine_id": "MC-001", "locked_fields": ["machine_id"], "confirmed_machine_id": "MC-001"},
        None,
    )
    assert rf.machine_id == "MC-001"
    assert slots.is_locked("machine_id")


def test_retrieval_snapshot_includes_session_slots() -> None:
    doc = _doc("warning text")
    snapshot = build_retrieval_snapshot(
        question_raw="แล้วต้องหยุดเครื่องไหม",
        question_retrieval="machine_id MC-001 แล้วต้องหยุดเครื่องไหม",
        question_synthesis="คำถามต่อเนื่อง",
        fallback_level=0,
        docs=[doc],
        rewrite_meta={"strategy": "rules", "follow_up": True},
        session_slots={"machine_id": "MC-001"},
        retrieval_report={"intent": "procedure"},
    )
    assert snapshot["session_slots"]["machine_id"] == "MC-001"
    assert snapshot["rewrite_strategy"] == "rules"
    assert snapshot["retrieval_report"]["intent"] == "procedure"


def test_production_profile_has_rewrite_enabled_by_default() -> None:
    from spark.core.production_profile import ProductionProfile

    profile = ProductionProfile.hardened_defaults()
    assert profile.query_rewrite_enabled is True


@pytest.mark.asyncio
async def test_session_slots_apply_turn_persists_chunk_memory() -> None:
    slots = SessionSlots(machine_id="MC-001")
    rf = RAGFilter(machine_id="MC-001", document_type="machine_manual")
    updated = slots.apply_turn(
        question="แล้วต้องหยุดเครื่องไหม",
        rf=rf,
        chunk_ids=["chunk-a", "chunk-b"],
    )
    assert updated.last_retrieved_chunk_ids == ["chunk-a", "chunk-b"]
    assert updated.last_user_question == "แล้วต้องหยุดเครื่องไหม"


def test_follow_up_detects_thai_short_continuation() -> None:
    assert is_follow_up_question(
        "แล้วต้องหยุดเครื่องไหม",
        [("human", "Servo MC-001 ร้อนผิดปกติ")],
        has_prior_user_message=True,
    )
