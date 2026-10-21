from __future__ import annotations

import pytest

from spark.retrieval.scoring import _retrieval_identity
from spark.services.rag_service import (
    RAGFilter,
    RAGService,
    RetrievedDoc,
    reciprocal_rank_fusion,
)


def _doc(chunk_id: str, *, vector: float = 0.0, lexical: float = 0.0, mode: str = "vector") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=f"content-{chunk_id}",
        score=max(vector, lexical),
        vector_score=vector,
        lexical_score=lexical,
        payload={"chunk_id": chunk_id, "retrieval_mode": mode},
    )


def test_rrf_rank_based_not_magnitude_based() -> None:
    # Lexical synthetic score (0.95) is larger than the dense cosine (0.40), but the
    # dense doc is rank #1 in the vector list, so RRF must not let raw magnitude win.
    vector = [_doc("v1", vector=0.40, mode="vector"), _doc("v2", vector=0.35, mode="vector")]
    lexical = [_doc("l1", lexical=0.95, mode="postgres_lexical")]

    fused = reciprocal_rank_fusion([vector, lexical], k=60, identity_fn=_retrieval_identity)

    # v1 (#1 vector) and l1 (#1 lexical) both top their single list → equal RRF.
    by_id = {d.payload["chunk_id"]: d for d in fused}
    assert by_id["v1"].fusion_score == pytest.approx(by_id["l1"].fusion_score)
    assert by_id["v1"].fusion_score > by_id["v2"].fusion_score


def test_rrf_rewards_documents_ranked_in_both_lists() -> None:
    shared_vec = _doc("shared", vector=0.5, mode="vector")
    shared_lex = _doc("shared", lexical=0.6, mode="postgres_lexical")
    vector = [shared_vec, _doc("v_only", vector=0.9, mode="vector")]
    lexical = [shared_lex, _doc("l_only", lexical=0.9, mode="postgres_lexical")]

    fused = reciprocal_rank_fusion([vector, lexical], k=60, identity_fn=_retrieval_identity)

    top = fused[0]
    assert top.payload["chunk_id"] == "shared"
    # Rank #1 in both lists → normalized score 1.0.
    assert top.fusion_score == pytest.approx(1.0)
    # "v_only" is rank #2 in a single list: (1/(k+2)) / (num_lists/(k+1)).
    single = next(d for d in fused if d.payload["chunk_id"] == "v_only")
    expected_rank2_single = (1.0 / 62) / (2.0 / 61)
    assert single.fusion_score == pytest.approx(expected_rank2_single)
    assert single.fusion_score < top.fusion_score


def test_rrf_dedup_merges_retrieval_modes_and_preserves_signals() -> None:
    vector = [_doc("c1", vector=0.7, mode="vector")]
    lexical = [_doc("c1", lexical=0.9, mode="postgres_lexical")]

    fused = reciprocal_rank_fusion([vector, lexical], k=60, identity_fn=_retrieval_identity)

    assert len(fused) == 1
    doc = fused[0]
    assert doc.vector_score == 0.7
    assert doc.lexical_score == 0.9
    assert set(doc.payload["retrieval_modes"]) == {"vector", "postgres_lexical"}
    assert doc.fusion_score == pytest.approx(1.0)


def test_rrf_normalized_score_in_unit_interval() -> None:
    vector = [_doc(f"v{i}", vector=1.0 - i * 0.01, mode="vector") for i in range(20)]
    lexical = [_doc(f"l{i}", lexical=0.99 - i * 0.01, mode="postgres_lexical") for i in range(20)]

    fused = reciprocal_rank_fusion([vector, lexical], k=60, identity_fn=_retrieval_identity)

    assert all(0.0 <= (d.fusion_score or -1) <= 1.0 for d in fused)
    assert fused == sorted(fused, key=lambda d: d.fusion_score or 0.0, reverse=True)


def test_rrf_empty_inputs() -> None:
    assert reciprocal_rank_fusion([], k=60, identity_fn=_retrieval_identity) == []
    assert reciprocal_rank_fusion([[], []], k=60, identity_fn=_retrieval_identity) == []


def test_rrf_invalid_k() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[_doc("c1", vector=0.5)]], k=0, identity_fn=_retrieval_identity)


@pytest.mark.asyncio
async def test_retrieve_uses_rrf_when_strategy_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    lexical_doc = _doc("lex", lexical=0.95, mode="postgres_lexical_v2")
    vector_doc = RetrievedDoc(
        page_content="v",
        score=0.42,
        vector_score=0.42,
        payload={"chunk_id": "vec", "page_content": "v", "retrieval_mode": "vector"},
    )

    async def fake_lexical(*_args, **_kwargs):
        return [lexical_doc], False

    from spark.retrieval.vector.qdrant_search import VectorSearchResult

    async def fake_vector(*_args, **_kwargs):
        return VectorSearchResult(hits=[vector_doc])

    async def passthrough_rerank(_query, docs, _top_k, **kwargs):
        return docs

    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_vector)
    monkeypatch.setattr(svc.retrieval_engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(svc, "_apply_retrieval_rerank_async", passthrough_rerank)
    monkeypatch.setattr("spark.core.config.settings.rag_rrf_k", 60)

    docs = await svc._retrieve("MC-001 ร้อน", RAGFilter(), top_k=5)

    assert docs
    assert all(d.fusion_score is not None for d in docs)


def test_cross_document_select_uses_authoritative_cross_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cross-encoder is available it is authoritative: a low-fusion doc that
    the cross-encoder rates highly must outrank a high-fusion doc it rates poorly."""
    import spark.services.reranker as reranker

    low_fusion_high_ce = RetrievedDoc(
        page_content="exact answer: bearing SKF 6205 every 5000 hours",
        score=0.3,
        vector_score=0.0,
        lexical_score=0.3,
        fusion_score=0.3,
        payload={"chunk_id": "ce_hit", "doc_id": "d1", "document_type": "machine_manual"},
    )
    high_fusion_low_ce = RetrievedDoc(
        page_content="unrelated warranty boilerplate",
        score=1.0,
        vector_score=0.9,
        lexical_score=0.0,
        fusion_score=1.0,
        payload={"chunk_id": "ce_miss", "doc_id": "d2", "document_type": "machine_manual"},
    )

    def fake_ce(_query: str, doc_texts):
        # High relevance for the exact-answer chunk, near-zero for boilerplate.
        return [0.97 if "bearing" in t else 0.02 for t in doc_texts]

    monkeypatch.setattr(
        "spark.retrieval.rerank.diversify.cross_encoder_scores",
        fake_ce,
    )

    selected = reranker.cross_document_select(
        "bearing SKF 6205 replacement interval",
        [high_fusion_low_ce, low_fusion_high_ce],
        top_k=2,
    )

    assert selected[0].payload["chunk_id"] == "ce_hit"
    assert selected[0].score == pytest.approx(0.97)
    assert selected[1].score == pytest.approx(0.02)
