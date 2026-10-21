"""Tests for retrieval snapshot persistence (Phase 10)."""

from __future__ import annotations

import uuid

from spark.retrieval.models import RetrievedDoc
from spark.retrieval.retrieval_snapshot import build_retrieval_snapshot


def _doc(chunk_id: str, doc_id: str, score: float, generation: int = 2) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="cooling fan check",
        score=score,
        vector_score=score,
        payload={
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "ingest_generation": generation,
        },
    )


def test_build_retrieval_snapshot_shape() -> None:
    chunk_a = str(uuid.uuid4())
    doc_a = str(uuid.uuid4())
    docs = [_doc(chunk_a, doc_a, 0.91, generation=3)]
    snapshot = build_retrieval_snapshot(
        question_raw="แล้วต้องหยุดเครื่องไหม",
        question_retrieval="machine_id MC-001 แล้วต้องหยุดเครื่องไหม",
        question_synthesis="แล้วต้องหยุดเครื่องไหม",
        fallback_level=1,
        docs=docs,
        fusion_method="rrf",
        rewrite_meta={"strategy": "rules", "follow_up": True},
    )
    assert snapshot["question_retrieval"].startswith("machine_id")
    assert snapshot["question_synthesis"] == "แล้วต้องหยุดเครื่องไหม"
    assert snapshot["fallback_level"] == 1
    assert snapshot["chunk_ids"] == [chunk_a]
    assert snapshot["scores"] == [0.91]
    assert snapshot["fusion_method"] == "rrf"
    assert snapshot["ingest_generations"] == {doc_a: 3}
    assert snapshot["rewrite"]["follow_up"] is True
