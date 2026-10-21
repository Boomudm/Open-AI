"""Backward-compatible re-exports — implementation lives in ``spark.retrieval.rerank``."""

from __future__ import annotations

from collections.abc import Sequence

from spark.retrieval.rerank.cross_encoder import cross_encoder as reranker_service
from spark.retrieval.rerank.diversify import (
    cross_document_rerank_ms,
    cross_document_select,
    lexical_overlap_score,
)


def cross_encoder_scores(query: str, doc_texts: Sequence[str]) -> list[float] | None:
    """Absolute cross-encoder relevance in [0,1], or None when the model is unavailable."""
    return reranker_service.score_pairs(query, doc_texts)


__all__ = [
    "cross_document_rerank_ms",
    "cross_document_select",
    "cross_encoder_scores",
    "lexical_overlap_score",
]
