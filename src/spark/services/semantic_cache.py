"""Semantic similarity cache for RAG queries.

Extends the existing VerifiedQACache with embedding-based similarity lookup.
When a new question is semantically similar (above threshold) to a previously
verified answer, the cached answer is returned — saving retrieval + LLM cost.

The `question_embedding` column already exists on `VerifiedQACache`.
This module populates it during verification and queries it during lookup.

Configuration:
    SEMANTIC_CACHE_ENABLED=true
    SEMANTIC_CACHE_THRESHOLD=0.92    (cosine similarity threshold)
    SEMANTIC_CACHE_MAX_CANDIDATES=50 (max cached entries to compare per factory)
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import semantic_cache_hit_total, semantic_cache_miss_total, semantic_cache_similarity
from spark.core.security import Principal
from spark.db.models.qa_cache import VerifiedQACache

log = get_logger(__name__)


class SemanticCacheConfig:
    def __init__(self) -> None:
        self.enabled = settings.semantic_cache_enabled or os.getenv("SEMANTIC_CACHE_ENABLED", "").lower() in ("1", "true")
        self.threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", str(settings.semantic_cache_threshold)))
        self.max_candidates = int(os.getenv("SEMANTIC_CACHE_MAX_CANDIDATES", str(settings.semantic_cache_max_candidates)))

    @classmethod
    def from_env(cls) -> SemanticCacheConfig:
        return cls()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


async def _embed_question(question: str) -> list[float]:
    from spark.ingestion.index.embedder import Embedder
    embedder = Embedder.get()
    return await embedder.embed_query(question)


async def semantic_cache_lookup(
    db: AsyncSession,
    *,
    factory_id: str | None,
    question: str,
    principal: Principal | None,
    machine_id: str | None = None,
    config: SemanticCacheConfig | None = None,
) -> dict[str, Any] | None:
    """Look up a semantically similar cached answer.

    Returns the cached answer dict if similarity >= threshold, else None.
    This is called BEFORE the exact-match QACacheService.lookup.
    """
    cfg = config or SemanticCacheConfig.from_env()
    if not cfg.enabled or not factory_id:
        return None

    try:
        query_embedding = await _embed_question(question)
    except Exception as exc:
        log.warning("semantic_cache_embed_failed", error=str(exc)[:300])
        return None

    stmt = (
        select(VerifiedQACache)
        .where(
            VerifiedQACache.factory_id == factory_id,
            VerifiedQACache.verification_method == "admin",
            VerifiedQACache.question_embedding.isnot(None),
        )
        .order_by(VerifiedQACache.hit_count.desc())
        .limit(cfg.max_candidates)
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        semantic_cache_miss_total.inc()
        return None

    best_score = 0.0
    best_row: VerifiedQACache | None = None

    from spark.ingestion.embed_profile import EmbedProfile

    current_version = EmbedProfile.from_runtime().version

    for row in rows:
        cached_embedding = row.question_embedding
        if not cached_embedding or not isinstance(cached_embedding, list):
            continue
        if len(cached_embedding) != len(query_embedding):
            continue

        row_model_version = getattr(row, "embed_model_version", None)
        if row_model_version is not None and row_model_version != current_version:
            continue

        sim = cosine_similarity(query_embedding, cached_embedding)

        if row_model_version is None:
            effective_threshold = min(0.98, cfg.threshold + 0.05)
            if sim < effective_threshold:
                continue

        if sim > best_score:
            best_score = sim
            best_row = row

    semantic_cache_similarity.observe(best_score)

    if best_score >= cfg.threshold and best_row is not None:
        if principal and not principal.is_admin and factory_id not in principal.factory_access:
            semantic_cache_miss_total.inc()
            return None

        from datetime import UTC, datetime
        if best_row.expires_at and best_row.expires_at < datetime.now(tz=UTC):
            semantic_cache_miss_total.inc()
            return None

        best_row.hit_count = int(best_row.hit_count or 0) + 1
        await db.flush()
        semantic_cache_hit_total.inc()
        log.info(
            "semantic_cache_hit",
            factory_id=factory_id,
            cache_id=str(best_row.cache_id),
            similarity=round(best_score, 4),
            original_question=best_row.question_text[:100],
        )
        return {
            "answer": best_row.answer_text,
            "sources": best_row.sources or [],
            "cache_hit": True,
            "semantic_cache_hit": True,
            "cache_id": str(best_row.cache_id),
            "similarity_score": round(best_score, 4),
            "filter_fingerprint": best_row.filter_fingerprint,
            "source_doc_ids": [str(item) for item in (best_row.source_doc_ids or [])],
        }

    semantic_cache_miss_total.inc()
    return None


async def store_question_embedding(
    db: AsyncSession,
    cache_id: str,
    question: str,
) -> None:
    """Store the question embedding for a verified cache entry.

    Called after QACacheService.verify_message to populate the embedding.
    """
    try:
        import uuid
        stmt = select(VerifiedQACache).where(VerifiedQACache.cache_id == uuid.UUID(cache_id))
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return
        if row.question_embedding is not None:
            return
        embedding = await _embed_question(question)
        row.question_embedding = embedding
        await db.flush()
        log.info("semantic_cache_embedding_stored", cache_id=cache_id)
    except Exception as exc:
        log.warning("semantic_cache_embedding_failed", cache_id=cache_id, error=str(exc)[:300])
