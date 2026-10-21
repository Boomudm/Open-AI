"""Table-aware PDF extraction helpers using pdfplumber."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger

log = get_logger(__name__)

_CELL_WS_RE = re.compile(r"\s+")


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = _CELL_WS_RE.sub(" ", str(value)).strip()
    return text.replace("|", "\\|")


def table_rows_to_markdown(rows: list[list[Any]]) -> str:
    """Convert pdfplumber table rows into a GitHub-flavored Markdown table."""
    cleaned: list[list[str]] = []
    for row in rows or []:
        if not row:
            continue
        cells = [_clean_cell(cell) for cell in row]
        if not any(cells):
            continue
        cleaned.append(cells)
    if not cleaned:
        return ""

    max_cols = max(len(row) for row in cleaned)
    normalized = [row + [""] * (max_cols - len(row)) for row in cleaned]

    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def extract_page_tables_markdown(pdf_path: Path, page_index: int) -> str:
    """Extract all tables on a zero-based page index as Markdown blocks."""
    try:
        import pdfplumber
    except ImportError:
        return ""

    blocks: list[str] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_index < 0 or page_index >= len(pdf.pages):
                return ""
            page = pdf.pages[page_index]
            tables = page.extract_tables() or []
            for table_idx, table in enumerate(tables, start=1):
                markdown = table_rows_to_markdown(table)
                if markdown:
                    blocks.append(f"#### Table {table_idx}\n\n{markdown}")
    except Exception as exc:
        log.warning(
            "pdf_table_extract_failed",
            file=str(pdf_path),
            page=page_index + 1,
            error=str(exc)[:200],
        )
        return ""

    if not blocks:
        return ""
    return "\n\n".join(blocks)


def merge_page_text_and_tables(page_text: str, tables_markdown: str) -> tuple[str, bool]:
    """Append structured table Markdown after body text when tables are present."""
    body = (page_text or "").strip()
    tables = (tables_markdown or "").strip()
    if not tables:
        return body, False
    if not body:
        return f"### Tables\n\n{tables}", True
    return f"{body}\n\n### Tables\n\n{tables}", True
