"""Regression: markdown spec-table evidence must keep its row structure.

Before this fix, `_trim_evidence_text` / `format_extractive_with_citations`
collapsed ALL whitespace (`re.sub(r"\\s+", " ", text)`), including the
newlines between rows of a PDF-extracted markdown table (see
spark.ingestion.parsers.pdf_tables.table_rows_to_markdown, which emits one
row per line). That flattened a multi-row parameter table into a single
unreadable line of "|" characters in the chat answer.
"""

from __future__ import annotations

from spark.generation.evidence_spans import EvidenceSpan, format_extractive_with_citations
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.synthesis import _collapse_horizontal_whitespace, _trim_evidence_text

_TABLE_TEXT = (
    "| Parameter ID | Name | Setting range | Initial value |\n"
    "| --- | --- | --- | --- |\n"
    "| 01A0h | Driver temperature information | 40 to 85 °C | 85 |\n"
    "| 01A1h | Overload time information | 1 to 300 (1=0.1 s) | 50 |"
)


def _doc(text: str, *, chunk_id: str = "chunk-1") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": "machine_manual",
            "source_file": "Oriental_Servo_Manual.pdf",
            "page": 157,
        },
    )


def test_collapse_horizontal_whitespace_keeps_line_breaks() -> None:
    messy = "  | a |   b |  \n\n  | --- | --- |  \n  | 1 |   2 |  "
    cleaned = _collapse_horizontal_whitespace(messy)
    assert cleaned == "| a | b |\n| --- | --- |\n| 1 | 2 |"


def test_trim_evidence_text_preserves_table_rows() -> None:
    trimmed = _trim_evidence_text(_TABLE_TEXT, max_chars=1000)
    assert trimmed.count("\n") == 3
    assert "01A1h | Overload time information" in trimmed.splitlines()[3]


def test_format_extractive_with_citations_keeps_table_rows_separate() -> None:
    doc = _doc(_TABLE_TEXT)
    span = EvidenceSpan(chunk_id="chunk-1", text=_TABLE_TEXT, doc=doc, score=0.9)

    answer, cited_docs = format_extractive_with_citations([span])

    assert cited_docs == [doc]
    row_lines = [line for line in answer.splitlines() if line.strip().startswith("|")]
    # Header + separator + 2 data rows must survive as four distinct lines,
    # not get glued into one unreadable line of "|" characters.
    assert len(row_lines) == 4
    assert row_lines[0].startswith("| Parameter ID")
    assert row_lines[-1].startswith("| 01A1h")
