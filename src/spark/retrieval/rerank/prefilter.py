"""Cascade pre-filter — cap candidates before cross-encoder scoring."""

from __future__ import annotations

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.retrieval.models import RetrievedDoc

log = get_logger(__name__)


def prefilter_candidates(docs: list[RetrievedDoc], top_k: int) -> list[RetrievedDoc]:
    """Keep top fusion-scored candidates up to rag_rerank_max_candidates."""
    max_candidates = max(int(top_k), int(settings.rag_rerank_max_candidates or 0))
    if max_candidates <= 0 or len(docs) <= max_candidates:
        return docs
    capped = sorted(docs, key=lambda d: d.score, reverse=True)[:max_candidates]
    log.info(
        "rag_rerank_candidates_capped",
        candidates=len(docs),
        capped_to=len(capped),
    )
    return capped
