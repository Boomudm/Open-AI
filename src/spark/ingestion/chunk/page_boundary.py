"""Page-faithful chunking policy (remediation v3 Phase 1)."""

from __future__ import annotations

from spark.ingestion.chunk.types import ChunkLeaf

SAFETY_PAGE_FAITHFUL_DOC_TYPES: frozenset[str] = frozenset(
    {"machine_manual", "sop", "safety_certificate"}
)


def requires_page_faithful_chunks(document_type: str | None) -> bool:
    return (document_type or "").strip().lower() in SAFETY_PAGE_FAITHFUL_DOC_TYPES


def is_page_aware_parent_child_strategy(strategy: str | None) -> bool:
    from spark.ingestion.chunk.strategies import normalize_chunk_strategy

    return normalize_chunk_strategy(strategy) == "page_aware_parent_child"


def assert_page_faithful_leaves(
    pairs: list[tuple[ChunkLeaf, dict[str, object]]],
    *,
    document_type: str | None,
) -> None:
    """Raise if safety doc types emit cross-page leaf metadata."""
    if not requires_page_faithful_chunks(document_type):
        return
    for leaf, meta in pairs:
        page = meta.get("page")
        if page is None:
            raise ValueError(
                f"page-faithful doc type {document_type!r} requires page on every chunk"
            )
        if leaf.page_number is not None and leaf.page_number != page:
            raise ValueError(
                f"chunk page mismatch: leaf={leaf.page_number} meta={page}"
            )


def group_blocks_by_page(blocks: list) -> dict[int, list]:
    """Group ParsedBlock instances by page number."""
    grouped: dict[int, list] = {}
    for block in blocks:
        page = int(block.page or 0)
        if page <= 0:
            continue
        grouped.setdefault(page, []).append(block)
    return grouped
