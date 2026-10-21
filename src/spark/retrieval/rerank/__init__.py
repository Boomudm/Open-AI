"""Rerank pipeline — CE scoring, diversification, relevance gates."""

from spark.retrieval.rerank.cross_encoder import (
    CrossEncoderReranker,
    RerankCacheContext,
    RerankerService,
    cross_encoder,
    reranker_service,
)
from spark.retrieval.rerank.diversify import cross_document_select, lexical_overlap_score
from spark.retrieval.rerank.gate import GateResult, apply_rerank_gate, passes_authoritative_relevance_gate
from spark.retrieval.rerank.gates_config import GateThresholds, load_rerank_gates_config
from spark.retrieval.rerank.pipeline import RerankPipeline, RerankResult, get_rerank_pipeline

__all__ = [
    "CrossEncoderReranker",
    "GateResult",
    "GateThresholds",
    "RerankCacheContext",
    "RerankPipeline",
    "RerankResult",
    "RerankerService",
    "apply_rerank_gate",
    "cross_document_select",
    "cross_encoder",
    "get_rerank_pipeline",
    "lexical_overlap_score",
    "load_rerank_gates_config",
    "passes_authoritative_relevance_gate",
    "reranker_service",
]
