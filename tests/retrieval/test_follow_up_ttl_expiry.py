"""Phase 11 — follow-up boost disabled after evidence TTL turns."""

from __future__ import annotations

import uuid

from spark.retrieval.preprocess.follow_up_boost import boost_follow_up_chunks
from spark.retrieval.models import RetrievedDoc
from spark.services.session_slots import SessionSlots


def _doc(chunk_id: str) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="LOTO step",
        score=0.5,
        vector_score=0.5,
        payload={"chunk_id": chunk_id},
    )


def test_session_evidence_age_from_context() -> None:
    slots = SessionSlots(
        last_retrieved_chunk_ids=[str(uuid.uuid4())],
        turn_count=6,
        last_evidence_turn=2,
        evidence_turn_ttl=3,
    )
    assert slots.evidence_age_turns() == 4
    assert SessionSlots.evidence_age_from_context(slots.to_context_dict()) == 4


def test_follow_up_boost_disabled_after_ttl_turns() -> None:
    chunk_id = str(uuid.uuid4())
    doc = _doc(chunk_id)
    unchanged = boost_follow_up_chunks(
        [doc],
        chunk_ids=[chunk_id],
        follow_up=True,
        question="tell me more",
        evidence_age_turns=4,
        evidence_turn_ttl=3,
    )
    assert unchanged[0].score == doc.score

    boosted = boost_follow_up_chunks(
        [doc],
        chunk_ids=[chunk_id],
        follow_up=True,
        question="tell me more",
        evidence_age_turns=2,
        evidence_turn_ttl=3,
    )
    assert boosted[0].score > doc.score
