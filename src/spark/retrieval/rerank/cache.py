"""Session-scoped rerank score cache with ingest-generation keying (Phase 8)."""

from __future__ import annotations

from spark.core.cache import Cache, cache_key
from spark.core.logging import get_logger
from spark.services.qa_cache_service import question_hash

log = get_logger(__name__)

RERANK_CACHE_TTL_SEC = 600


def _generation_suffix(generation: int | None) -> str:
    return str(generation if generation is not None else 1)


async def get_cached_rerank_scores(
    session_id: str,
    question: str,
    chunk_ids: list[str],
    *,
    generations: list[int | None] | None = None,
) -> dict[str, float]:
    if not session_id or not chunk_ids:
        return {}
    q_hash = question_hash(question)
    cache = Cache.get()
    out: dict[str, float] = {}
    for idx, chunk_id in enumerate(chunk_ids):
        gen = (
            generations[idx]
            if generations is not None and idx < len(generations)
            else None
        )
        key = cache_key("rerank", session_id, q_hash, chunk_id, _generation_suffix(gen))
        value = await cache.get_json(key)
        if isinstance(value, (int, float)):
            out[chunk_id] = float(value)
    return out


async def store_rerank_scores(
    session_id: str,
    question: str,
    scores_by_chunk: dict[str, float],
    *,
    generations_by_chunk: dict[str, int | None] | None = None,
    ttl: int = RERANK_CACHE_TTL_SEC,
) -> None:
    if not session_id or not scores_by_chunk:
        return
    q_hash = question_hash(question)
    cache = Cache.get()
    for chunk_id, score in scores_by_chunk.items():
        gen = (generations_by_chunk or {}).get(chunk_id)
        key = cache_key("rerank", session_id, q_hash, chunk_id, _generation_suffix(gen))
        await cache.set_json(key, float(score), ttl=ttl)


async def invalidate_rerank_cache_for_chunks(chunk_ids: list[str]) -> None:
    """Delete rerank cache entries referencing any of the given chunk_ids."""
    if not chunk_ids:
        return
    try:
        from spark.core.cache import Cache
        cache = Cache()
        client = await cache._client()
        if not client:
            return
        deleted = 0
        for chunk_id in chunk_ids:
            pattern = f"spark:rerank:*{chunk_id}*"
            async for key in client.scan_iter(match=pattern, count=100):
                await client.delete(key)
                deleted += 1
        if deleted:
            log.info("rerank_cache_invalidated", chunks=len(chunk_ids), keys_deleted=deleted)
    except Exception as exc:
        log.warning("rerank_cache_invalidation_failed", error=str(exc)[:200])
