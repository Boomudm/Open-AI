"""Lexical retrieval protocol."""

from __future__ import annotations

from typing import Protocol

from spark.retrieval.models import RAGFilter, RetrievedDoc


class LexicalEngine(Protocol):
    async def search(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        *,
        allowed_doc_ids: list[str] | None = None,
    ) -> list[RetrievedDoc]: ...
