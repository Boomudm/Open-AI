"""Contract: Phase 7 fusion + rerank serving."""

from __future__ import annotations


def test_fusion_v2_and_reranker_service_exports() -> None:
    from spark.retrieval.fusion import fuse_candidates, fuse_two_lists
    from spark.retrieval.fusion import fuse_candidates as legacy_fuse
    from spark.services.reranker_service import RerankerService, reranker_service

    assert callable(fuse_candidates)
    assert callable(fuse_two_lists)
    assert legacy_fuse is fuse_candidates
    assert isinstance(reranker_service, RerankerService)


def test_factory_config_supports_fusion_weights() -> None:
    from spark.retrieval.tuning import RagFusionConfig

    cfg = RagFusionConfig.from_factory_config(
        {
            "rag": {
                "fusion_method": "weighted_rrf",
                "dense_weight": 0.7,
                "lexical_weight": 0.3,
            }
        }
    )
    assert cfg.dense_weight == 0.7
    assert cfg.lexical_weight == 0.3
    assert cfg.method == "weighted_rrf"
