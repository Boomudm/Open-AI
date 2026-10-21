"""Dense-only vector search for enterprise/HR collection."""

from __future__ import annotations


from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from spark.core.config import settings
from spark.core.qdrant import DENSE_VECTOR_NAME, get_async_qdrant_client
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.vector.qdrant_search import EmbedderProtocol, VectorSearchResult


def _build_enterprise_filter(
    rf: RAGFilter,
    allowed_doc_ids: list[str] | None = None,
) -> Filter | None:
    must: list[FieldCondition | Filter] = []

    if allowed_doc_ids is not None:
        must.append(
            FieldCondition(key="doc_id", match=MatchAny(any=allowed_doc_ids))
        )
    if rf.factory_id:
        must.append(FieldCondition(key="factory_id", match=MatchValue(value=rf.factory_id)))
    if rf.document_type:
        must.append(FieldCondition(key="document_type", match=MatchValue(value=rf.document_type)))
    if rf.language:
        must.append(FieldCondition(key="language", match=MatchValue(value=rf.language)))

    must.append(FieldCondition(key="retrieval_enabled", match=MatchValue(value=True)))

    return Filter(must=must) if must else None


async def search_enterprise_dense(
    *,
    query: str,
    rf: RAGFilter,
    top_k: int,
    embedder: EmbedderProtocol,
    allowed_doc_ids: list[str] | None = None,
) -> VectorSearchResult:
    """Dense-only search against the enterprise Qdrant collection."""
    collection = settings.qdrant_enterprise_collection
    initial_k = max(top_k, top_k * settings.rag_retrieve_multiplier)
    qfilter = _build_enterprise_filter(rf, allowed_doc_ids=allowed_doc_ids)

    try:
        vector = await embedder.embed_query(query)
    except Exception:
        return VectorSearchResult(hits=[], failed_collections=[collection], embed_failed=True)

    client = get_async_qdrant_client()

    try:
        response = await client.query_points(
            collection_name=collection,
            query=vector,
            using=DENSE_VECTOR_NAME,
            limit=initial_k,
            query_filter=qfilter,
            with_payload=True,
        )
        hits: list[RetrievedDoc] = []
        for point in response.points:
            payload = dict(point.payload or {})
            score = float(point.score) if point.score is not None else 0.0
            hits.append(
                RetrievedDoc(
                    page_content=str(payload.get("page_content", "")),
                    score=score,
                    vector_score=score,
                    payload=payload,
                )
            )
        return VectorSearchResult(hits=hits, sparse_encoder_id="none")
    except Exception as exc:
        from spark.core.logging import get_logger
        log = get_logger(__name__)
        log.warning("enterprise_search_failed", collection=collection, error=str(exc)[:200])
        return VectorSearchResult(hits=[], failed_collections=[collection])
