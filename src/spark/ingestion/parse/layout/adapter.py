"""Layout parser protocol (remediation v3 Phase 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from spark.ingestion.parse.layout.types import LayoutPage, LayoutTable


class LayoutParser(Protocol):
    name: str

    def parse(self, pdf_path: Path) -> tuple[int, list[LayoutPage], list[LayoutTable]]: ...


def get_layout_parser(parser_name: str | None = None) -> LayoutParser:
    from spark.core.config import settings

    name = (parser_name or settings.spark_layout_parser or "fallback_pypdf").strip().lower()
    if name == "docling":
        from spark.ingestion.parse.layout.docling_adapter import DoclingLayoutParser

        return DoclingLayoutParser()
    from spark.ingestion.parse.layout.fallback_pypdf import PyPdfLayoutParser

    return PyPdfLayoutParser()
