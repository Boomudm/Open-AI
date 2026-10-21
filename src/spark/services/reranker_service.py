"""Backward-compatible re-exports — implementation lives in ``spark.retrieval.rerank``."""

from __future__ import annotations

from spark.retrieval.rerank.cross_encoder import (
    CrossEncoderReranker,
    RerankCacheContext,
    RerankerService,
    cross_encoder,
    reranker_service,
    validate_gpu_rerank_at_startup,
)

__all__ = [
    "CrossEncoderReranker",
    "RerankCacheContext",
    "RerankerService",
    "cross_encoder",
    "reranker_service",
    "validate_gpu_rerank_at_startup",
]
