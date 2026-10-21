"""Phase 6 — deterministic chunk IDs survive re-ingest."""

from __future__ import annotations

import uuid

from spark.ingestion.chunk.registry import chunk_text_leaves
from spark.ingestion.chunk.stable_id import stable_chunk_id, stable_parent_chunk_id, section_path_tuple
from spark.ingestion.chunk.table import table_to_leaf
from spark.ingestion.parse.table_object import TableObject


def test_stable_chunk_id_is_deterministic() -> None:
    doc_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    path = ("Cooling", "Fan")
    first = stable_chunk_id(doc_id, path, 0)
    second = stable_chunk_id(doc_id, path, 0)
    third = stable_chunk_id(doc_id, path, 1)
    assert first == second
    assert first != third


def test_reingest_produces_identical_leaf_chunk_ids() -> None:
    doc_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    text = "Section A\n\n1. Inspect the cooling fan.\n\n2. Verify temperature below 80C."
    first = chunk_text_leaves(
        text,
        strategy="sop_procedure",
        chunk_size=400,
        chunk_overlap=40,
        doc_id=doc_id,
    )
    second = chunk_text_leaves(
        text,
        strategy="sop_procedure",
        chunk_size=400,
        chunk_overlap=40,
        doc_id=doc_id,
    )
    assert [leaf.chunk_id for leaf in first] == [leaf.chunk_id for leaf in second]
    assert [leaf.parent_chunk_id for leaf in first] == [leaf.parent_chunk_id for leaf in second]


def test_table_row_uses_stable_id_not_random() -> None:
    doc_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    table = TableObject(
        markdown="| Part | Qty |\n| --- | --- |\n| BRG-01 | 2 |",
        headers=["Part", "Qty"],
        rows=[["BRG-01", "2"]],
        page=1,
        table_index=3,
    )
    leaf_a = table_to_leaf(table, doc_id=doc_id)
    leaf_b = table_to_leaf(table, doc_id=doc_id)
    assert leaf_a.chunk_id == leaf_b.chunk_id
    assert leaf_a.parent_chunk_id == leaf_b.parent_chunk_id
    expected = str(stable_chunk_id(doc_id, section_path_tuple("Table 3"), 3))
    assert leaf_a.chunk_id == expected
    assert leaf_a.parent_chunk_id == str(stable_parent_chunk_id(doc_id, section_path_tuple("Table 3")))
