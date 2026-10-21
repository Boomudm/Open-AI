"""Structured table blocks extracted from PDF pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


def _rows_to_dicts(headers: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in rows:
        record = {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}
        if any(record.values()):
            records.append(record)
    return records


@dataclass(frozen=True)
class TableObject:
    markdown: str
    headers: list[str]
    rows: list[dict[str, str]]
    page: int
    table_index: int = 1
    extraction_strategy: str = "lines"

    def to_embed_text(self) -> str:
        parts = [f"Table page {self.page}"]
        if self.headers:
            parts.append("Columns: " + ", ".join(self.headers))
        parts.append(self.markdown)
        return "\n".join(parts)

    def to_payload(self) -> dict[str, Any]:
        part_numbers = [
            v
            for row in self.rows
            for k, v in row.items()
            if v and ("part" in k.lower() or "รหัส" in k or "ชิ้นส่วน" in k)
        ]
        payload: dict[str, Any] = {
            "block_type": "table",
            "page": self.page,
            "table_index": self.table_index,
            "table_headers": self.headers,
            "table_row_count": len(self.rows),
            "part_numbers": part_numbers,
            "has_tables": True,
        }
        if self.extraction_strategy != "lines":
            # "text"-strategy tables are reconstructed from whitespace alignment
            # (no ruling lines) — usable, but less reliable than a ruled table,
            # and known to reproduce upstream PDF text-layer corruption verbatim
            # (e.g. cross-row character interleaving seen in real factory exports).
            payload["extraction_confidence"] = "positional_reconstruction"
        return payload


_TEXT_STRATEGY_SETTINGS = {"vertical_strategy": "text", "horizontal_strategy": "text"}


def _extract_tables_with_fallback(page: Any) -> tuple[list[list[list[Any]]], str]:
    """Default lines-based extraction, falling back to text-alignment for borderless tables.

    pdfplumber's default table strategy requires visible ruling lines. Factory
    exports (e.g. PLC I/O mapping sheets printed to PDF) are often column-aligned
    plain text with zero rects/lines — those never match "lines" but are usually
    still recoverable via "text" strategy, which groups cells by whitespace gaps.
    """
    tables = page.extract_tables() or []
    if tables:
        return tables, "lines"
    try:
        return page.extract_tables(table_settings=_TEXT_STRATEGY_SETTINGS) or [], "text"
    except Exception:
        return [], "lines"


def extract_page_tables(pdf_path: Path, page_index: int) -> list[TableObject]:
    """Extract structured tables from a zero-based page index."""
    try:
        import pdfplumber
    except ImportError:
        return []

    objects: list[TableObject] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_index < 0 or page_index >= len(pdf.pages):
                return []
            page = pdf.pages[page_index]
            tables, strategy = _extract_tables_with_fallback(page)
            for table_idx, table in enumerate(tables, start=1):
                cleaned: list[list[str]] = []
                for row in table or []:
                    cells = [_clean_cell(cell) for cell in row]
                    if any(cells):
                        cleaned.append(cells)
                if not cleaned:
                    continue
                headers = cleaned[0]
                body_rows = cleaned[1:]
                markdown = table_rows_to_markdown(cleaned)
                if not markdown:
                    continue
                objects.append(
                    TableObject(
                        markdown=markdown,
                        headers=headers,
                        rows=_rows_to_dicts(headers, body_rows),
                        page=page_index + 1,
                        table_index=table_idx,
                        extraction_strategy=strategy,
                    )
                )
    except Exception as exc:
        log.warning(
            "pdf_table_extract_failed",
            file=str(pdf_path),
            page=page_index + 1,
            error=str(exc)[:200],
        )
    return objects


def extract_all_tables_batch(pdf_path: Path) -> list[TableObject]:
    """Open PDF once and extract tables from all pages."""
    try:
        import pdfplumber
    except ImportError:
        return []

    objects: list[TableObject] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                try:
                    tables, strategy = _extract_tables_with_fallback(page)
                    for table_idx, table in enumerate(tables, start=1):
                        cleaned: list[list[str]] = []
                        for row in table or []:
                            cells = [_clean_cell(cell) for cell in row]
                            if any(cells):
                                cleaned.append(cells)
                        if not cleaned:
                            continue
                        headers = cleaned[0]
                        body_rows = cleaned[1:]
                        markdown = table_rows_to_markdown(cleaned)
                        if not markdown:
                            continue
                        objects.append(
                            TableObject(
                                markdown=markdown,
                                headers=headers,
                                rows=_rows_to_dicts(headers, body_rows),
                                page=page_index + 1,
                                table_index=table_idx,
                                extraction_strategy=strategy,
                            )
                        )
                except Exception as exc:
                    log.warning("table_extract_page_error", page=page_index, error=str(exc)[:200])
    except Exception as exc:
        log.warning("table_extract_batch_error", path=str(pdf_path), error=str(exc)[:200])
    return objects


def extract_all_tables(pdf_path: Path) -> list[TableObject]:
    """Extract tables from every page in a PDF."""
    return extract_all_tables_batch(pdf_path)
