"""Phase 12 — follow-up evidence boost decays after TTL turns."""

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


def test_session_follow_up_chunks_expire_after_ttl() -> None:
    chunk_id = str(uuid.uuid4())
    slots = SessionSlots(
        last_retrieved_chunk_ids=[chunk_id],
        turn_count=5,
        last_evidence_turn=1,
        evidence_turn_ttl=3,
    )
    assert slots.follow_up_chunk_ids() == []
    assert slots.evidence_age_turns() == 4


def test_session_follow_up_chunks_available_within_ttl() -> None:
    chunk_id = str(uuid.uuid4())
    slots = SessionSlots(
        last_retrieved_chunk_ids=[chunk_id],
        turn_count=3,
        last_evidence_turn=2,
        evidence_turn_ttl=3,
    )
    assert slots.follow_up_chunk_ids() == [chunk_id]


def test_follow_up_boost_respects_evidence_age() -> None:
    chunk_id = str(uuid.uuid4())
    doc = _doc(chunk_id)
    boosted = boost_follow_up_chunks(
        [doc],
        chunk_ids=[chunk_id],
        follow_up=True,
        question="follow up question",
        evidence_age_turns=4,
        evidence_turn_ttl=3,
    )
    assert boosted[0].score == doc.score

    boosted_active = boost_follow_up_chunks(
        [doc],
        chunk_ids=[chunk_id],
        follow_up=True,
        question="follow up question",
        evidence_age_turns=2,
        evidence_turn_ttl=3,
    )
    assert boosted_active[0].score > doc.score
