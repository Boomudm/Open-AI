"""Qdrant dense+sparse hybrid search — global multi-shard RRF (Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from spark.core.config import settings
from spark.core.qdrant import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    qdrant_retry_async,
    reset_async_qdrant_client,
    sparse_vectors_enabled,
)
from spark.core.qdrant_strategy import list_search_collections, validate_factory_id_for_retrieval
from spark.retrieval.vector.filters import build_exact_tag_filter, build_qdrant_filter
from spark.retrieval.vector.generation_filter import filter_active_ingest_docs
from spark.retrieval.vector.shard_search import search_all_shards
from spark.retrieval.models import RAGFilter, RetrievedDoc


class EmbedderProtocol(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


@dataclass
class VectorSearchResult:
    hits: list[RetrievedDoc] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    embed_failed: bool = False
    sparse_encoder_id: str = ""


async def search_qdrant_hybrid(
    *,
    query: str,
    rf: RAGFilter,
    top_k: int,
    embedder: EmbedderProtocol,
    get_client: Any,
    ensure_collection: Any,
    allowed_doc_ids: list[str] | None = None,
) -> VectorSearchResult:
    """Search scoped collections; merge shards with global RRF before app fusion."""
    validate_factory_id_for_retrieval(rf.factory_id)
    initial_k = max(top_k, top_k * settings.rag_retrieve_multiplier)
    qfilter = build_qdrant_filter(rf, allowed_doc_ids=allowed_doc_ids)
    collections = list_search_collections(rf.factory_id, rf.document_category)

    try:
        vector = await embedder.embed_query(query)
    except Exception:
        return VectorSearchResult(hits=[], failed_collections=collections, embed_failed=True)

    client = get_client()
    use_hybrid_qdrant = sparse_vectors_enabled()
    sparse_encoder_id = "none"
    sparse_query = None
    if use_hybrid_qdrant:
        from spark.contracts.sparse_encoding_contract import retrieval_sparse_encoder

        sparse_encoder = retrieval_sparse_encoder()
        sparse_encoder_id = sparse_encoder.encoder_id
        sparse_query = sparse_encoder.encode_query(query)

    async def _search_one_collection(coll: str) -> list[RetrievedDoc]:
        ensure_collection(coll, vector_size=len(vector))

        async def _query() -> list[RetrievedDoc]:
            if use_hybrid_qdrant and sparse_query and sparse_query.indices:
                from qdrant_client.models import Fusion, FusionQuery, Prefetch

                response = await client.query_points(
                    collection_name=coll,
                    prefetch=[
                        Prefetch(
                            query=vector,
                            using=DENSE_VECTOR_NAME,
                            limit=initial_k,
                            filter=qfilter,
                        ),
                        Prefetch(
                            query=sparse_query,
                            using=SPARSE_VECTOR_NAME,
                            limit=initial_k,
                            filter=qfilter,
                        ),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=initial_k,
                    with_payload=True,
                )
                results = response.points
            else:
                results = await client.search(
                    collection_name=coll,
                    query_vector=(DENSE_VECTOR_NAME, vector),
                    query_filter=qfilter,
                    limit=initial_k,
                    with_payload=True,
                )

            hits: list[RetrievedDoc] = []
            for r in results:
                payload = dict(r.payload or {})
                payload.setdefault("retrieval_mode", "vector")
                hits.append(
                    RetrievedDoc(
                        page_content=payload.get("page_content", ""),
                        score=float(r.score),
                        vector_score=float(r.score),
                        payload=payload,
                    )
                )
            return hits

        try:
            return await qdrant_retry_async(_query)
        except (ConnectionError, OSError):
            reset_async_qdrant_client()
            raise

    raw_hits, failed = await search_all_shards(
        collections=collections,
        search_one=_search_one_collection,
        limit=initial_k,
        factory_id=rf.factory_id,
    )
    filtered = await filter_active_ingest_docs(raw_hits)
    return VectorSearchResult(
        hits=filtered,
        failed_collections=failed,
        embed_failed=False,
        sparse_encoder_id=sparse_encoder_id,
    )


async def search_qdrant_exact_tag(
    tag: str,
    rf: RAGFilter,
    top_k: int,
    *,
    get_client: Any,
    allowed_doc_ids: list[str] | None = None,
) -> list[RetrievedDoc]:
    """Scroll Qdrant for an exact PLC/IO tag on either symlink side."""
    if not str(tag or "").strip():
        return []
    validate_factory_id_for_retrieval(rf.factory_id)
    qfilter = build_exact_tag_filter(tag, rf, allowed_doc_ids=allowed_doc_ids)
    collections = list_search_collections(rf.factory_id, rf.document_category)
    limit = max(1, top_k)
    client = get_client()

    async def _search_one_collection(coll: str) -> list[RetrievedDoc]:
        async def _query() -> list[RetrievedDoc]:
            response = await client.scroll(
                collection_name=coll,
                scroll_filter=qfilter,
                limit=limit,
                with_payload=True,
            )
            points = response[0] if isinstance(response, tuple) else getattr(response, "points", response)
            hits: list[RetrievedDoc] = []
            for point in points or []:
                payload = dict(getattr(point, "payload", None) or {})
                payload.setdefault("retrieval_mode", "exact_tag")
                hits.append(
                    RetrievedDoc(
                        page_content=payload.get("page_content", ""),
                        score=1.0,
                        vector_score=0.0,
                        lexical_score=1.0,
                        payload=payload,
                    )
                )
            return hits

        try:
            return await qdrant_retry_async(_query)
        except (ConnectionError, OSError):
            reset_async_qdrant_client()
            raise

    raw_hits, _failed = await search_all_shards(
        collections=collections,
        search_one=_search_one_collection,
        limit=limit,
        factory_id=rf.factory_id,
    )
    return await filter_active_ingest_docs(raw_hits)
