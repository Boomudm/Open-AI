"""pypdf/pdfplumber layout parser — dev/test fallback (Phase 1)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from pypdf import PdfReader

from spark.core.logging import get_logger
from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage, LayoutTable
from spark.ingestion.parse.table_object import extract_page_tables

log = get_logger(__name__)

DEFAULT_MIN_CHARS_PER_PAGE = 20

_SINGLE_THAI = re.compile(r"^[฀-๿]$")


def _is_per_char_spaced(text: str) -> bool:
    """True when pypdf extracted Thai text as individual space-separated characters.

    Some PDFs with non-standard font encodings cause pypdf to emit each glyph
    separately: 'ย ง จ ะ' instead of 'ยังจะ'. Detected when >60% of
    space-delimited tokens are single Thai codepoints (requires ≥20 tokens).
    """
    tokens = text.split()
    if len(tokens) < 20:
        return False
    single_thai = sum(1 for t in tokens if _SINGLE_THAI.match(t))
    return single_thai / len(tokens) > 0.60


def _collapse_per_char_spacing(text: str) -> str:
    """Collapse 'ย ง จ ะ ด ั ก' → 'ยังจะดัก', keeping multi-char tokens separate."""
    tokens = text.split()
    result: list[str] = []
    run: list[str] = []
    for token in tokens:
        if _SINGLE_THAI.match(token):
            run.append(token)
        else:
            if run:
                result.append("".join(run))
                run = []
            result.append(token)
    if run:
        result.append("".join(run))
    return " ".join(result)


def fix_char_spacing(text: str) -> str:
    """Apply per-character spacing fix if the page text needs it."""
    if _is_per_char_spaced(text):
        fixed = _collapse_per_char_spacing(text)
        log.debug("pypdf_char_spacing_fixed", before_len=len(text), after_len=len(fixed))
        return fixed
    return text


def _page_needs_ocr(text: str, min_chars: int) -> bool:
    return len((text or "").strip()) < min_chars


def extract_pages_raw(pdf_path: Path) -> tuple[int, list[tuple[int, str, str]]]:
    """Extract page text with pypdf, then pdfplumber for pages pypdf cannot read."""
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    pages: list[tuple[int, str, str]] = []
    empty_indexes: list[int] = []

    for page_idx in range(page_count):
        text = fix_char_spacing(reader.pages[page_idx].extract_text() or "")
        if text.strip():
            pages.append((page_idx + 1, text, "pypdf"))
        else:
            pages.append((page_idx + 1, "", "pypdf"))
            empty_indexes.append(page_idx)

    if empty_indexes:
        try:
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_idx in empty_indexes:
                    if page_idx >= len(pdf.pages):
                        continue
                    fallback_text = fix_char_spacing(pdf.pages[page_idx].extract_text() or "")
                    if fallback_text.strip():
                        pages[page_idx] = (page_idx + 1, fallback_text, "pdfplumber")
        except Exception as exc:
            log.warning("pdfplumber_fallback_failed", file=str(pdf_path), error=str(exc)[:200])

    return page_count, pages


class PyPdfLayoutParser:
    name = "fallback_pypdf"

    def parse(self, pdf_path: Path) -> tuple[int, list[LayoutPage], list[LayoutTable]]:
        page_count, raw_pages = extract_pages_raw(pdf_path)
        layout_pages: list[LayoutPage] = []
        for order, (page_num, page_text, source) in enumerate(raw_pages):
            blocks: list[LayoutBlock] = []
            if page_text.strip():
                blocks.append(
                    LayoutBlock(
                        block_id=str(uuid.uuid4()),
                        page_number=page_num,
                        block_type="text",
                        text=page_text,
                        extraction_source=source,
                    )
                )
            layout_pages.append(
                LayoutPage(
                    page_number=page_num,
                    blocks=blocks,
                    extraction_source=source,
                )
            )

        tables: list[LayoutTable] = []
        for page_index in range(page_count):
            for table_obj in extract_page_tables(pdf_path, page_index):
                row_values = [[str(v) for v in row.values()] for row in table_obj.rows]
                if table_obj.headers:
                    row_values = [table_obj.headers] + row_values
                tables.append(
                    LayoutTable(
                        page_number=table_obj.page,
                        table_index=table_obj.table_index,
                        headers=list(table_obj.headers),
                        rows=row_values,
                        markdown=table_obj.markdown,
                    )
                )

        return page_count, layout_pages, tables
