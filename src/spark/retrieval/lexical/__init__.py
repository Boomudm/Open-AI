"""Lexical retrieval engine — postgres_thai_v3 (Phase 6)."""

from __future__ import annotations

from typing import Literal

from spark.retrieval.models import RAGFilter, RetrievedDoc

from .postgres_thai_v3 import PostgresThaiV3LexicalEngine

RetrievalLexicalEngine = Literal["postgres_thai_v3"]

_ENGINE = PostgresThaiV3LexicalEngine()


def get_lexical_retriever(
    engine: RetrievalLexicalEngine | str = "postgres_thai_v3",
) -> PostgresThaiV3LexicalEngine:
    if str(engine) != "postgres_thai_v3":
        raise ValueError(f"unsupported lexical engine {engine!r}; use postgres_thai_v3")
    return _ENGINE


async def retrieve_lexical_candidates(
    query: str,
    rf: RAGFilter,
    top_k: int,
    *,
    allowed_doc_ids: list[str] | None = None,
    engine: RetrievalLexicalEngine | str = "postgres_thai_v3",
) -> list[RetrievedDoc]:
    return await get_lexical_retriever(engine).search(
        query,
        rf,
        top_k,
        allowed_doc_ids=allowed_doc_ids,
    )


__all__ = [
    "PostgresThaiV3LexicalEngine",
    "RetrievalLexicalEngine",
    "get_lexical_retriever",
    "retrieve_lexical_candidates",
]
