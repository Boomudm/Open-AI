"""Multi-shard vector search — parallel collection queries with global RRF merge (Phase 8)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from spark.core.metrics import rag_vector_collection_fail_total
from spark.retrieval.candidates import retrieval_identity
from spark.retrieval.fusion import fuse_candidates
from spark.retrieval.common import log
from spark.retrieval.models import RetrievedDoc

SearchOneShard = Callable[[str], Awaitable[list[RetrievedDoc]]]


def global_rrf_merge(
    shard_hits: list[list[RetrievedDoc]],
    *,
    k: int = 60,
) -> list[RetrievedDoc]:
    """Merge per-shard hit lists with rank-based RRF — never fuse raw cross-shard scores."""
    lists = [group for group in shard_hits if group]
    if not lists:
        return []
    if len(lists) == 1:
        return list(lists[0])
    return fuse_candidates(
        lists,
        method="rrf",
        rrf_k=k,
        identity_fn=retrieval_identity,
    )


async def search_all_shards(
    *,
    collections: list[str],
    search_one: SearchOneShard,
    limit: int,
    rrf_k: int = 60,
    factory_id: str | None = None,
) -> tuple[list[RetrievedDoc], list[str]]:
    """Search collections in parallel and merge with global RRF."""

    async def _search_shard(coll: str) -> tuple[str, list[RetrievedDoc] | None]:
        try:
            hits = await search_one(coll)
            return coll, hits
        except Exception as exc:
            log.error(
                "qdrant_collection_search_failed",
                collection=coll,
                factory_id=factory_id,
                error=str(exc)[:500],
                exception_class=type(exc).__name__,
                exc_info=True,
            )
            rag_vector_collection_fail_total.labels(collection=coll).inc()
            return coll, None

    if not collections:
        return [], []

    outcomes = await asyncio.gather(*[_search_shard(coll) for coll in collections])
    failed: list[str] = []
    hit_lists: list[list[RetrievedDoc]] = []
    for coll, hits in outcomes:
        if hits is None:
            failed.append(coll)
            continue
        hit_lists.append(hits)

    merged = global_rrf_merge(hit_lists, k=rrf_k)
    if limit > 0:
        merged = merged[:limit]
    return merged, failed
