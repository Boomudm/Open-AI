"""Execute lexical SQL and map rows to RetrievedDoc."""

from __future__ import annotations

import time

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document, DocumentChunk
from spark.retrieval.common import log
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.scoring import _keyword_recovery_score


def chunk_to_retrieved(
    query: str,
    chunk: DocumentChunk,
    document: Document,
    *,
    retrieval_mode: str,
    db_rank: float | None = None,
) -> RetrievedDoc | None:
    payload = dict(chunk.payload or {})
    payload.setdefault("doc_id", str(document.doc_id))
    payload.setdefault("chunk_id", str(chunk.chunk_id))
    payload.setdefault("chunk_index", chunk.chunk_index)
    payload.setdefault("page", chunk.page)
    payload.setdefault("factory_id", document.factory_id)
    payload.setdefault("machine_id", document.machine_id)
    payload.setdefault("component_id", document.component_id)
    payload.setdefault("document_category", document.document_category)
    payload.setdefault("document_type", document.document_type)
    payload.setdefault("language", document.language)
    payload.setdefault("revision", document.revision)
    payload.setdefault("source_file", document.source_file)
    payload.setdefault("title", document.title)
    payload.setdefault("page_content", chunk.content or "")
    if chunk.parent_content:
        payload["parent_content"] = chunk.parent_content
    if chunk.boost_tokens:
        payload["boost_tokens"] = list(chunk.boost_tokens)

    keyword_score = _keyword_recovery_score(query, payload)
    if db_rank is not None and db_rank > 0:
        score = max(keyword_score, float(db_rank))
    else:
        score = keyword_score
    if score < float(settings.rag_lexical_min_score):
        return None
    payload.setdefault("retrieval_mode", retrieval_mode)
    return RetrievedDoc(
        page_content=chunk.content or "",
        score=score,
        vector_score=0.0,
        lexical_score=score,
        payload=payload,
    )


async def execute_lexical_query(
    stmt,
    query: str,
    *,
    retrieval_mode: str,
    source: str,
    top_k: int,
    start: float,
    rank_column: str = "combined_rank",
) -> list[RetrievedDoc]:
    candidates: list[RetrievedDoc] = []
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).all()
    for row in rows:
        chunk, document = row[0], row[1]
        db_rank = float(row[2] if len(row) > 2 else 0.0)
        doc = chunk_to_retrieved(
            query,
            chunk,
            document,
            retrieval_mode=retrieval_mode,
            db_rank=db_rank,
        )
        if doc is not None:
            candidates.append(doc)
    target = max(top_k, top_k * settings.rag_retrieve_multiplier)
    candidates.sort(key=lambda d: d.score, reverse=True)
    result = candidates[:target]
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "rag_retrieval_path",
        source=source,
        candidates=len(candidates),
        returned=len(result),
        latency_ms=latency_ms,
        retrieval_mode=retrieval_mode,
    )
    return result
