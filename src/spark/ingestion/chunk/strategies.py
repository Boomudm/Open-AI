"""Chunk strategy factory — sole registry entry point (Phase 6)."""

from __future__ import annotations

from spark.ingestion.chunk.semantic_heading import SemanticHeadingChunker
from spark.ingestion.chunk.sop_procedure import SopProcedureChunker
from spark.ingestion.chunk.table import TableChunker
from spark.ingestion.chunk.table_row import TableRowChunker
from spark.ingestion.chunk.types import DEPRECATED_STRATEGY_ALIASES, ChunkingStrategy
from spark.ingestion.chunking.recursive import recursive_chunk_text
from spark.ingestion.chunking.structure import split_structure_aware


class RecursiveChunker:
    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        return recursive_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


class StructureAwareChunker:
    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        return split_structure_aware(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def normalize_chunk_strategy(name: str | None) -> str:
    normalized = (name or "recursive").lower()
    return DEPRECATED_STRATEGY_ALIASES.get(normalized, normalized)


def get_chunking_strategy(name: str | None) -> ChunkingStrategy:
    normalized = normalize_chunk_strategy(name)
    if normalized == "semantic_heading":
        return SemanticHeadingChunker()
    if normalized == "sop_procedure":
        return SopProcedureChunker()
    if normalized == "table_row":
        return TableRowChunker()
    if normalized == "table":
        return TableChunker()
    if normalized == "structure_aware":
        return StructureAwareChunker()
    if normalized == "page_aware_parent_child":
        from spark.ingestion.chunk.parent_child import ParentChildChunker

        return ParentChildChunker()
    return RecursiveChunker()


def is_parent_child_strategy(name: str | None) -> bool:
    return normalize_chunk_strategy(name) == "page_aware_parent_child"
