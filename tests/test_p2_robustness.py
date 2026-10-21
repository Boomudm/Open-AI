from __future__ import annotations

import uuid

from spark.ingestion.parsers.pdf_tables import (
    merge_page_text_and_tables,
    table_rows_to_markdown,
)
from spark.generation.context import build_grounded_context
from spark.generation.citations import validate_grounded_citations
from spark.retrieval.models import RetrievedDoc
from spark.generation.parent_context import (
    generation_context_for_doc,
    group_docs_for_generation,
)


def test_table_rows_to_markdown_formats_spec_sheet() -> None:
    rows = [
        ["Part No.", "Torque (Nm)", "Notes"],
        ["BOLT-M8", "25", "Apply thread lock"],
        ["BOLT-M10", "45", "Check twice"],
    ]
    md = table_rows_to_markdown(rows)
    assert "| Part No. | Torque (Nm) | Notes |" in md
    assert "| BOLT-M8 | 25 | Apply thread lock |" in md
    assert "| --- | --- | --- |" in md


def test_table_rows_to_markdown_escapes_pipes() -> None:
    md = table_rows_to_markdown([["A|B", "Value"]])
    assert r"A\|B" in md


def test_table_rows_to_markdown_skips_empty_rows() -> None:
    assert table_rows_to_markdown([["", ""], None]) == ""


def test_merge_page_text_and_tables_appends_section() -> None:
    body = "Motor specification overview."
    tables = "| Spec | Value |\n| --- | --- |\n| RPM | 3000 |"
    merged, has_tables = merge_page_text_and_tables(body, tables)
    assert has_tables is True
    assert "### Tables" in merged
    assert "Motor specification overview." in merged
    assert "| RPM | 3000 |" in merged


def test_merge_page_text_and_tables_tables_only() -> None:
    merged, has_tables = merge_page_text_and_tables("", "| A | B |")
    assert has_tables is True
    assert merged.startswith("### Tables")


def _child_doc(
    child_text: str,
    parent_text: str,
    *,
    parent_chunk_id: str | None = None,
    chunk_id: str | None = None,
) -> RetrievedDoc:
    pid = parent_chunk_id or str(uuid.uuid4())
    return RetrievedDoc(
        page_content=child_text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id or str(uuid.uuid4()),
            "parent_chunk_id": pid,
            "parent_content": parent_text,
            "document_type": "datasheet",
            "source_file": "spec.pdf",
            "page": 2,
        },
    )


def test_generation_context_for_doc_uses_parent() -> None:
    doc = _child_doc("torque 25 Nm", "Full table section with torque 25 Nm and notes.")
    assert generation_context_for_doc(doc) == "Full table section with torque 25 Nm and notes."


def test_group_docs_for_generation_deduplicates_parent() -> None:
    parent_id = str(uuid.uuid4())
    doc_a = _child_doc("row A", "PARENT BODY", parent_chunk_id=parent_id)
    doc_b = _child_doc("row B", "PARENT BODY", parent_chunk_id=parent_id)
    groups = group_docs_for_generation([doc_a, doc_b])
    assert len(groups) == 1
    assert groups[0][1] == "PARENT BODY"
    assert len(groups[0][0]) == 2


def test_group_docs_splits_colliding_parent_id_with_different_content() -> None:
    # Real corpus case (KUKA p.57 vs p.58): the chunker assigned ONE parent id
    # to two DIFFERENT parent windows. Collapsing on id alone handed the model
    # group[0]'s table while citing both children — the other child's evidence
    # silently vanished and the model "denied" facts it never saw.
    parent_id = str(uuid.uuid4())
    doc_a = _child_doc(
        "During operation -5 C to 45 C", "BASE spec table with ambient temp",
        parent_chunk_id=parent_id,
    )
    doc_b = _child_doc(
        "During storage -20 C to 60 C", "4CAB variant table without ambient temp",
        parent_chunk_id=parent_id,
    )
    groups = group_docs_for_generation([doc_a, doc_b])
    assert len(groups) == 2
    texts = {g[1] for g in groups}
    assert texts == {
        "BASE spec table with ambient temp",
        "4CAB variant table without ambient temp",
    }


def test_build_grounded_context_expands_to_parent() -> None:
    parent_id = str(uuid.uuid4())
    doc = _child_doc("child snippet", "PARENT CONTEXT WITH TABLE ROWS", parent_chunk_id=parent_id)
    ctx = build_grounded_context([doc])
    assert "PARENT CONTEXT WITH TABLE ROWS" in ctx
    assert "child snippet" not in ctx
    assert f"chunk_id:{doc.payload['chunk_id']}" in ctx


def test_validate_grounded_citations_checks_parent_content() -> None:
    doc = _child_doc("25 Nm", "Torque spec: 25 Nm for bolt M8.")
    cid = doc.payload["chunk_id"]
    ok, _ = validate_grounded_citations(
        f"แรงบิด 25 Nm [chunk_id:{cid}]",
        [doc],
    )
    assert ok is True

    bad, _ = validate_grounded_citations(
        f"แรงบิด 99 Nm [chunk_id:{cid}]",
        [doc],
    )
    assert bad is False
