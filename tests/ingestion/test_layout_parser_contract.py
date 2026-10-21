"""Layout parser contract tests (remediation v3 Phase 1)."""

from __future__ import annotations

from pathlib import Path

from spark.ingestion.parse.layout import get_layout_parser
from spark.ingestion.parse.layout.fallback_pypdf import PyPdfLayoutParser, extract_pages_raw


def test_get_layout_parser_fallback_default() -> None:
    parser = get_layout_parser("fallback_pypdf")
    assert parser.name == "fallback_pypdf"


def test_pypdf_layout_parser_returns_page_numbers(tmp_path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "layout_test.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 720, "Page one content")
    c.showPage()
    c.drawString(72, 720, "Page two content")
    c.showPage()
    c.save()

    page_count, layout_pages, tables = PyPdfLayoutParser().parse(pdf_path)
    assert page_count == 2
    assert len(layout_pages) == 2
    assert layout_pages[0].page_number == 1
    assert layout_pages[1].page_number == 2
    assert "Page one" in layout_pages[0].blocks[0].text
    assert tables == []


def test_extract_pages_raw_backward_compatible(tmp_path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "raw_pages.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 720, "hello")
    c.save()

    page_count, pages = extract_pages_raw(pdf_path)
    assert page_count == 1
    assert pages[0][0] == 1
    assert "hello" in pages[0][1]
