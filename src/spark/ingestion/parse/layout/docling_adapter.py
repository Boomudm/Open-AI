"""Docling layout parser — primary production path (Phase 1).

Falls back to pypdf when docling is not installed (test/dev). Production lock
requires ``layout_parser: docling``; install docling separately for full layout.
"""

from __future__ import annotations

from pathlib import Path

from spark.core.logging import get_logger
from spark.ingestion.parse.layout.fallback_pypdf import PyPdfLayoutParser
from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage, LayoutTable

log = get_logger(__name__)


class DoclingLayoutParser:
    name = "docling"

    def parse(self, pdf_path: Path) -> tuple[int, list[LayoutPage], list[LayoutTable]]:
        try:
            return self._parse_docling(pdf_path)
        except ImportError:
            log.warning(
                "docling_not_installed",
                file=str(pdf_path),
                detail="falling back to pypdf layout parser",
            )
            return PyPdfLayoutParser().parse(pdf_path)

    def _parse_docling(self, pdf_path: Path) -> tuple[int, list[LayoutPage], list[LayoutTable]]:
        # Optional dependency — real docling integration when package is added to pyproject.
        from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]

        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        doc = result.document
        layout_pages: list[LayoutPage] = []
        tables: list[LayoutTable] = []
        page_count = len(getattr(doc, "pages", []) or []) or 1

        for page_idx, page in enumerate(getattr(doc, "pages", []) or [], start=1):
            blocks = []
            for item in getattr(page, "items", []) or []:
                text = str(getattr(item, "text", "") or "").strip()
                if not text:
                    continue
                label = str(getattr(item, "label", "text") or "text").lower()
                block_type = "heading" if "heading" in label or "title" in label else "text"
                blocks.append(
                    LayoutBlock(
                        block_id=f"p{page_idx}-{len(blocks)}",
                        page_number=page_idx,
                        block_type=block_type,
                        text=text,
                        extraction_source="docling",
                    )
                )
            layout_pages.append(
                LayoutPage(page_number=page_idx, blocks=blocks, extraction_source="docling")
            )

        if not layout_pages:
            return PyPdfLayoutParser().parse(pdf_path)

        return page_count, layout_pages, tables
