"""Chunk strategy registry — blocks and text to ChunkLeaf lists."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from spark.ingestion.chunk.section_path import section_path_for_chunk
from spark.ingestion.chunk.stable_id import (
    coerce_doc_id,
    section_path_tuple,
    stable_chunk_id,
    stable_parent_chunk_id,
)
from spark.ingestion.chunk.strategies import get_chunking_strategy, is_parent_child_strategy, normalize_chunk_strategy
from spark.ingestion.chunk.table import table_to_leaf
from spark.ingestion.chunk.types import ChunkLeaf
from spark.ingestion.parse.blocks import ParsedBlock
from spark.ingestion.parse.table_object import TableObject

PARSER_VERSION = "parse_v3"


def _semantic_embedding_allowed(*, offline_only: bool = False) -> bool:
    """Embedding breakpoint chunking is offline/benchmark-only (remediation v3 Phase 5)."""
    return bool(offline_only)


def _normalize_strategy(strategy: str | None) -> str:
    return normalize_chunk_strategy(strategy)


def _attach_stable_ids(
    leaf: ChunkLeaf,
    *,
    doc_id: uuid.UUID | None,
    leaf_index: int,
) -> ChunkLeaf:
    if doc_id is None:
        if not leaf.parent_chunk_id:
            return replace(leaf, parent_chunk_id=str(uuid.uuid4()))
        return leaf
    path_tuple = section_path_tuple(leaf.section_path)
    parent_id = leaf.parent_chunk_id or str(stable_parent_chunk_id(doc_id, path_tuple))
    chunk_id = leaf.chunk_id or str(stable_chunk_id(doc_id, path_tuple, leaf_index))
    return replace(leaf, parent_chunk_id=parent_id, chunk_id=chunk_id)


def chunk_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    *,
    strategy: str | None = None,
    semantic_breakpoint_threshold: float | None = None,
    offline_only: bool = False,
) -> list[str]:
    if not text:
        return []
    normalized = _normalize_strategy(strategy)
    if (
        normalized == "semantic_embedding"
        and semantic_breakpoint_threshold is not None
        and _semantic_embedding_allowed(offline_only=offline_only)
    ):
        from spark.ingestion.chunk.semantic import split_by_embedding_breakpoint

        return split_by_embedding_breakpoint(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            breakpoint_threshold=semantic_breakpoint_threshold,
        )
    return get_chunking_strategy(normalized).split(
        text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )


def chunk_text_leaves(
    text: str,
    *,
    strategy: str | None = None,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    parent_chunk_size: int = 2400,
    parent_chunk_overlap: int = 64,
    child_chunk_size: int = 512,
    child_chunk_overlap: int = 64,
    semantic_breakpoint_threshold: float | None = None,
    offline_only: bool = False,
    doc_id: uuid.UUID | str | None = None,
) -> list[ChunkLeaf]:
    """Return child leaves with parent sections for parent-child retrieval."""
    if not text.strip():
        return []

    normalized = _normalize_strategy(strategy)
    doc_uuid = coerce_doc_id(doc_id)

    if is_parent_child_strategy(strategy):
        from spark.ingestion.chunk.parent_child import ParentChildChunker

        leaves = ParentChildChunker().split_hierarchy(
            text,
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=parent_chunk_overlap,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
            doc_id=doc_uuid,
        )
        return leaves

    if normalized == "sop_procedure":
        from spark.ingestion.chunk.sop_procedure import split_sop_leaves

        leaves = split_sop_leaves(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return [
            _attach_stable_ids(leaf, doc_id=doc_uuid, leaf_index=index)
            for index, leaf in enumerate(leaves)
        ]

    if (
        normalized == "semantic_embedding"
        and semantic_breakpoint_threshold is not None
        and _semantic_embedding_allowed(offline_only=offline_only)
    ):
        from spark.ingestion.chunk.semantic import split_by_embedding_breakpoint

        flat = split_by_embedding_breakpoint(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            breakpoint_threshold=semantic_breakpoint_threshold,
        )
    else:
        flat = chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strategy=strategy,
            semantic_breakpoint_threshold=semantic_breakpoint_threshold,
            offline_only=offline_only,
        )

    leaves: list[ChunkLeaf] = []
    search_start = 0
    for parent_index, chunk in enumerate(flat):
        path, search_start = section_path_for_chunk(text, chunk, search_start)
        leaf = ChunkLeaf(
            text=chunk,
            parent_text=chunk,
            parent_index=parent_index,
            child_index=0,
            parent_chunk_id="",
            section_path=path,
            page_number=None,
        )
        leaves.append(_attach_stable_ids(leaf, doc_id=doc_uuid, leaf_index=parent_index))
    return leaves


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    strategy: str | None = None,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    parent_chunk_size: int = 2400,
    parent_chunk_overlap: int = 64,
    child_chunk_size: int = 512,
    child_chunk_overlap: int = 64,
    semantic_breakpoint_threshold: float | None = None,
    offline_only: bool = False,
    document_type: str | None = None,
    doc_id: uuid.UUID | str | None = None,
) -> list[tuple[ChunkLeaf, dict[str, Any]]]:
    """Chunk narrative blocks individually; emit table blocks as single leaves."""
    from spark.ingestion.chunk.page_boundary import assert_page_faithful_leaves
    from spark.ingestion.chunk.types import EXCEL_ONLY_CHUNK_STRATEGIES

    if _normalize_strategy(strategy) in EXCEL_ONLY_CHUNK_STRATEGIES:
        # table_row splits on blank lines — meaningful for Excel narrative rows,
        # but on a PDF/Word page block it yields one giant chunk per page
        # (observed: 14k-char chunks from the PDF twin of an IO-mapping sheet,
        # far past what the embedder can represent). A document type configured
        # for Excel can still receive a PDF upload via parser: auto.
        strategy = None

    doc_uuid = coerce_doc_id(doc_id)
    results: list[tuple[ChunkLeaf, dict[str, Any]]] = []

    # Global position counter across ALL blocks in this document.
    # chunk_text_leaves() resets leaf_index to 0 for each block; when
    # multiple blocks share the same (or empty) section_path that produces
    # identical UUID5 chunk_ids — a UniqueViolationError on document_chunks.
    # Using a document-level counter breaks the tie regardless of section_path.
    global_leaf_index = 0

    for block in blocks:
        if block.block_type == "table":
            table = block.metadata.get("table_object")
            if isinstance(table, TableObject):
                meta = {
                    "page": block.page,
                    "section_path": block.section_path,
                    "parser_version": block.metadata.get("parser_version"),
                    **block.metadata,
                }
                leaf = table_to_leaf(table, doc_id=doc_uuid, leaf_index=global_leaf_index)
                results.append((leaf, meta))
                global_leaf_index += 1
            elif block.text.strip():
                table_obj = TableObject(
                    markdown=block.text,
                    headers=block.metadata.get("headers") or [],
                    rows=block.metadata.get("rows") or [],
                    page=int(block.page or block.metadata.get("page") or 0),
                )
                leaf = table_to_leaf(table_obj, doc_id=doc_uuid, leaf_index=global_leaf_index)
                results.append((leaf, block.metadata))
                global_leaf_index += 1
            continue

        if not block.text.strip():
            continue

        block_meta = {
            "page": block.page,
            "section_path": block.section_path,
            "reading_order": block.reading_order,
            "parser_version": block.metadata.get("parser_version"),
            **block.metadata,
        }
        section_prefix = block.section_path if isinstance(block.section_path, str) else ""
        for leaf in chunk_text_leaves(
            block.text,
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=parent_chunk_overlap,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
            semantic_breakpoint_threshold=semantic_breakpoint_threshold,
            offline_only=offline_only,
            doc_id=doc_uuid,
        ):
            leaf_with_page = replace(
                leaf,
                section_path=leaf.section_path or section_prefix,
                page_number=block.page,
            )
            # Re-derive chunk_id using the global position so chunks from
            # different blocks with identical section_paths don't collide.
            if doc_uuid is not None:
                path_tuple = section_path_tuple(leaf_with_page.section_path)
                global_chunk_id = str(stable_chunk_id(doc_uuid, path_tuple, global_leaf_index))
                leaf_with_page = replace(leaf_with_page, chunk_id=global_chunk_id)
            global_leaf_index += 1
            merged_meta = dict(block_meta)
            if leaf_with_page.section_path and not merged_meta.get("section_path"):
                merged_meta["section_path"] = leaf_with_page.section_path
            results.append((leaf_with_page, merged_meta))

    assert_page_faithful_leaves(results, document_type=document_type)
    return results


def get_semantic_chunker(*, breakpoint_threshold: float = 0.5):
    from spark.ingestion.chunk.semantic import EmbeddingBreakpointChunker

    return EmbeddingBreakpointChunker(breakpoint_threshold=breakpoint_threshold)


def leaf_metadata_fields(leaf: ChunkLeaf) -> dict[str, Any]:
    """Optional parser payload fields derived from ChunkLeaf lineage."""
    fields: dict[str, Any] = {}
    if leaf.chunk_id:
        fields["chunk_id"] = leaf.chunk_id
    if leaf.step_index is not None:
        fields["step_index"] = leaf.step_index
    if leaf.block_type:
        fields["block_type"] = leaf.block_type
    return fields
