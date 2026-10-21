from __future__ import annotations

from spark.retrieval.fusion import fuse_candidates
from spark.retrieval.scoring import _retrieval_identity
from spark.services.rag_service import RetrievedDoc


def _doc(chunk_id: str, *, vector: float = 0.0, lexical: float = 0.0, mode: str = "vector") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=f"content-{chunk_id}",
        score=max(vector, lexical),
        vector_score=vector,
        lexical_score=lexical,
        payload={"chunk_id": chunk_id, "retrieval_mode": mode},
    )


def test_weighted_rrf_prefers_weighted_list() -> None:
    vector = [_doc("v1", vector=0.9), _doc("v2", vector=0.5)]
    lexical = [_doc("l1", lexical=0.95)]

    fused = fuse_candidates(
        [vector, lexical],
        method="weighted_rrf",
        weights=[0.9, 0.1],
        rrf_k=60,
        identity_fn=_retrieval_identity,
    )
    by_id = {d.payload["chunk_id"]: d for d in fused}
    assert by_id["v1"].fusion_score > by_id["l1"].fusion_score


def test_convex_fusion_uses_dense_alpha() -> None:
    vector = [_doc("v1", vector=0.8)]
    lexical = [_doc("l1", lexical=0.95)]

    fused = fuse_candidates(
        [vector, lexical],
        method="convex",
        weights=[0.7, 0.3],
        rrf_k=60,
        identity_fn=_retrieval_identity,
    )
    assert fused[0].payload["chunk_id"] == "v1"


def test_factory_fusion_config_weights() -> None:
    from spark.retrieval.tuning import RagFusionConfig

    cfg = RagFusionConfig.from_factory_config(
        {"rag": {"fusion_method": "convex", "dense_weight": 0.7, "lexical_weight": 0.3}}
    )
    assert cfg.method == "convex"
    assert cfg.weights_for_lists(2) == [0.7, 0.3]
