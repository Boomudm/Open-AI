"""Contract: factory fusion config is consumed by retrieval engine."""

from __future__ import annotations

from spark.retrieval.fusion_weights import resolve_hybrid_weights
from spark.retrieval.tuning import RagFusionConfig


def test_fusion_weights_merge_intent_and_factory_config() -> None:
    cfg = RagFusionConfig(method="weighted_rrf", dense_weight=0.5, lexical_weight=0.5)
    dense, lexical = resolve_hybrid_weights(0.8, 0.2, cfg)
    assert abs(dense + lexical - 1.0) < 1e-6
    assert dense > lexical


def test_rag_fusion_config_from_factory_defaults() -> None:
    cfg = RagFusionConfig.from_factory_config({})
    assert cfg.dense_weight == 0.7
    assert cfg.lexical_weight == 0.3
