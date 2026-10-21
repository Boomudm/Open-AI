"""Shared chunk types and strategy names (Phase 6 canonical)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

CANONICAL_CHUNK_STRATEGIES: frozenset[str] = frozenset(
    {
        "recursive",
        "structure_aware",
        "semantic_heading",
        "sop_procedure",
        "table",
        "table_row",
        "page_aware_parent_child",
    }
)

# Offline / benchmark-only strategies (require chunking.offline_only in config).
OFFLINE_CHUNK_STRATEGIES: frozenset[str] = frozenset({"semantic_embedding"})

# Rejected at config load — migrate YAML to canonical names.
DEPRECATED_CHUNK_STRATEGIES: frozenset[str] = frozenset(
    {
        "parent_child",
        "structure",
        "semantic",
        "per_row",
    }
)

DEPRECATED_STRATEGY_ALIASES: dict[str, str] = {
    "parent_child": "page_aware_parent_child",
    "structure": "structure_aware",
    "semantic": "semantic_heading",
    "per_row": "table_row",
}

CHUNK_STRATEGIES: frozenset[str] = CANONICAL_CHUNK_STRATEGIES | OFFLINE_CHUNK_STRATEGIES

CONFIG_ALLOWED_CHUNK_STRATEGIES: frozenset[str] = CHUNK_STRATEGIES

EXCEL_ONLY_CHUNK_STRATEGIES: frozenset[str] = frozenset({"table_row"})


@dataclass(frozen=True)
class ChunkLeaf:
    """Child chunk for embedding with its parent section for generation context."""

    text: str
    parent_text: str
    parent_index: int
    child_index: int
    parent_chunk_id: str
    section_path: str = ""
    page_number: int | None = None
    step_index: int | None = None
    block_type: str | None = None
    chunk_id: str | None = None


class ChunkingStrategy(Protocol):
    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]: ...
