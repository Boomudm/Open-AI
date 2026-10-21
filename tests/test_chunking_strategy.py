from __future__ import annotations

from spark.ingestion.chunk.parent_child import ParentChildChunker
from spark.ingestion.chunk.semantic_heading import SemanticHeadingChunker
from spark.ingestion.chunk.strategies import get_chunking_strategy
from spark.ingestion.chunk.registry import chunk_text_leaves


def test_semantic_heading_splits_on_headings() -> None:
    text = "# Section A\n\nParagraph one.\n\n## Section B\n\nParagraph two is longer."
    chunks = SemanticHeadingChunker().split(text, chunk_size=200, chunk_overlap=20)
    assert len(chunks) >= 2
    assert any("Section A" in c for c in chunks)
    assert any("Section B" in c for c in chunks)


def test_get_chunking_strategy_defaults_recursive() -> None:
    strategy = get_chunking_strategy(None)
    chunks = strategy.split("alpha beta gamma", chunk_size=5, chunk_overlap=0)
    assert len(chunks) >= 1


def test_parent_child_creates_multiple_children() -> None:
    text = " ".join(f"word{i}" for i in range(400))
    leaves = ParentChildChunker().split_hierarchy(
        text,
        parent_chunk_size=800,
        parent_chunk_overlap=0,
        child_chunk_size=120,
        child_chunk_overlap=20,
    )
    assert len(leaves) >= 3
    parent_ids = {leaf.parent_chunk_id for leaf in leaves}
    assert len(parent_ids) >= 1
    for leaf in leaves:
        assert leaf.text in leaf.parent_text
        assert len(leaf.text) <= 140


def test_parent_child_preserves_table_block_in_parent() -> None:
    text = (
        "Spec sheet\n\n"
        "| Part | Torque |\n| --- | --- |\n| M8 | 25 |\n| M10 | 45 |\n\n"
        "Notes: verify torque after assembly."
    )
    leaves = ParentChildChunker().split_hierarchy(
        text,
        parent_chunk_size=500,
        parent_chunk_overlap=0,
        child_chunk_size=80,
        child_chunk_overlap=0,
    )
    assert leaves
    assert "| M8 | 25 |" in leaves[0].parent_text
    assert any("| M10 | 45 |" in leaf.parent_text for leaf in leaves)


def test_chunk_text_leaves_flat_mode_wraps_parent() -> None:
    leaves = chunk_text_leaves("short text block", strategy="recursive", chunk_size=200, chunk_overlap=0)
    assert len(leaves) == 1
    assert leaves[0].text == leaves[0].parent_text
    assert leaves[0].parent_chunk_id


def test_get_chunking_strategy_parent_child() -> None:
    strategy = get_chunking_strategy("parent_child")
    chunks = strategy.split("one two three four five six", chunk_size=10, chunk_overlap=0)
    assert len(chunks) >= 1
