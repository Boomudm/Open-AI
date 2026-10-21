"""Postgres Thai v3 lexical retriever — dual FTS + trgm + industrial boosts."""

from __future__ import annotations

import time

from sqlalchemy import case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, TEXT

from spark.core.config import settings
from spark.db.models.docs import Document, DocumentChunk
from spark.retrieval.models import RAGFilter, RetrievedDoc

from .query_build import build_lexical_query_parts
from .rank import BOOST_TOKEN_WEIGHT, combined_lexical_rank
from .runtime import execute_lexical_query
from .scope import scope_filters


class PostgresThaiV3LexicalEngine:
    """Production lexical leg: Thai token FTS + simple FTS + pg_trgm + boost tokens."""

    async def search(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        *,
        allowed_doc_ids: list[str] | None = None,
    ) -> list[RetrievedDoc]:
        start = time.perf_counter()
        scan_limit = max(0, int(settings.rag_lexical_scan_limit or 0))
        if scan_limit <= 0:
            return []

        scope = scope_filters(rf, allowed_doc_ids)
        if scope is None:
            return []

        parts = build_lexical_query_parts(query)
        normalized = str(parts["normalized"])
        if not normalized:
            return []

        thai_text = str(parts["thai_text"] or "")
        latin_text = str(parts["latin_text"] or "")
        trgm_text = str(parts["trgm_text"] or normalized)
        boost_terms: list[str] = list(parts["boost_terms"] or [])

        content = func.coalesce(DocumentChunk.content, "")
        simple_tsv = func.coalesce(
            DocumentChunk.content_tsv,
            func.to_tsvector("simple", content),
        )
        thai_tsv = func.coalesce(
            DocumentChunk.content_tsv_th,
            func.to_tsvector("simple", func.coalesce(DocumentChunk.content_th_tokenized, "")),
        )

        simple_query_text = latin_text or normalized
        simple_tsquery = func.plainto_tsquery("simple", simple_query_text)
        simple_match = simple_tsv.op("@@")(simple_tsquery)
        simple_rank = func.ts_rank_cd(simple_tsv, simple_tsquery)

        if thai_text:
            thai_tsquery = func.plainto_tsquery("simple", thai_text)
            thai_match = thai_tsv.op("@@")(thai_tsquery)
            thai_rank = func.ts_rank_cd(thai_tsv, thai_tsquery)
        else:
            thai_match = literal(False)
            thai_rank = literal(0.0)

        similarity_score = func.similarity(content, trgm_text)
        trgm_floor = float(settings.rag_pg_trgm_similarity_floor)

        prefilters: list = [simple_match, thai_match, similarity_score >= trgm_floor]
        for term in boost_terms:
            prefilters.append(func.similarity(content, term) >= trgm_floor)
            prefilters.append(Document.machine_id == term)
            prefilters.append(Document.source_file.ilike(f"%{term}%"))
            prefilters.append(Document.title.ilike(f"%{term}%"))

        boost_overlap = None
        if boost_terms:
            boost_overlap = DocumentChunk.boost_tokens.op("&&")(
                cast(boost_terms, ARRAY(TEXT))
            )
            prefilters.append(boost_overlap)

        rank_expr = combined_lexical_rank(
            thai_fts_rank=thai_rank,
            simple_fts_rank=simple_rank,
            trgm_score=similarity_score,
        )
        if boost_overlap is not None:
            rank_expr = rank_expr + case(
                (boost_overlap, literal(BOOST_TOKEN_WEIGHT)),
                else_=literal(0.0),
            )

        stmt = (
            select(
                DocumentChunk,
                Document,
                rank_expr.label("combined_rank"),
            )
            .join(Document, Document.doc_id == DocumentChunk.doc_id)
            .where(*scope, or_(*prefilters))
            .order_by(rank_expr.desc(), DocumentChunk.created_at.desc())
            .limit(scan_limit)
        )
        return await execute_lexical_query(
            stmt,
            query,
            retrieval_mode="postgres_thai_v3",
            source="postgres_thai_v3",
            top_k=top_k,
            start=start,
            rank_column="combined_rank",
        )
