"""Global multi-shard RRF merge (remediation v2 Phase 8)."""

from __future__ import annotations

from spark.retrieval.vector.shard_search import global_rrf_merge
from spark.retrieval.models import RetrievedDoc


def _doc(chunk_id: str, score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=f"content-{chunk_id}",
        score=score,
        vector_score=score,
        payload={"chunk_id": chunk_id, "retrieval_mode": "vector"},
    )


def test_global_rrf_merge_prefers_high_rank_across_shards() -> None:
    shard_a = [_doc("shared", 0.99), _doc("a-only", 0.5)]
    shard_b = [_doc("shared", 0.1), _doc("b-only", 0.8)]
    merged = global_rrf_merge([shard_a, shard_b], k=60)
    chunk_ids = [doc.payload["chunk_id"] for doc in merged]
    assert chunk_ids[0] == "shared"
    assert set(chunk_ids) == {"shared", "a-only", "b-only"}


def test_global_rrf_merge_single_shard_passthrough() -> None:
    hits = [_doc("only", 0.7)]
    assert global_rrf_merge([hits]) == hits
