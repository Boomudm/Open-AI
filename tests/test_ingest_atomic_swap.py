"""Unit tests for per-page OCR and atomic ingest generation swap."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.ingest_swap import (
    IngestGenerationPlan,
    resolve_ingest_generation,
)
from spark.ingestion.parsers.image_ocr_parser import OCRPage
from spark.ingestion.parsers.pdf_parser import PDFParser, _apply_per_page_ocr_async


@pytest.mark.asyncio
async def test_apply_per_page_ocr_only_targets_sparse_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[int]] = {}

    def fake_ocr(_path, page_numbers, _ocr_cfg):
        captured["pages"] = page_numbers
        return {
            2: OCRPage(page_number=2, text="Scanned table values", confidence=88.0),
        }

    monkeypatch.setattr(
        "spark.ingestion.parsers.pdf_parser._run_ocr_pages",
        fake_ocr,
    )
    pages = [
        (1, "Digital page with enough extractable text content.", "pypdf"),
        (2, "", "pypdf"),
    ]
    updated, stats = await _apply_per_page_ocr_async(
        Path("mixed.pdf"),
        pages,
        {"min_chars_per_page": 20, "async": False},
    )

    assert captured["pages"] == [2]
    assert updated[0][2] == "pypdf"
    assert updated[1][1] == "Scanned table values"
    assert updated[1][2] == "ocr"
    assert stats["ocr_page_count"] == 1


@pytest.mark.asyncio
async def test_pdf_parser_uses_sparse_page_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage

    class FakeLayoutParser:
        name = "fake_layout"

        def parse(self, _path: Path):
            pages = [
                LayoutPage(
                    page_number=1,
                    extraction_source="pypdf",
                    blocks=[
                        LayoutBlock(
                            block_id="p1-b1",
                            page_number=1,
                            block_type="text",
                            text="Digital overview with enough text for direct chunking.",
                        )
                    ],
                ),
                LayoutPage(
                    page_number=2,
                    extraction_source="pypdf",
                    blocks=[
                        LayoutBlock(
                            block_id="p2-b1",
                            page_number=2,
                            block_type="text",
                            text="",
                        )
                    ],
                ),
            ]
            return 2, pages, []

    monkeypatch.setattr(
        "spark.ingestion.parsers.pdf_parser.get_layout_parser",
        lambda _name=None: FakeLayoutParser(),
    )
    monkeypatch.setattr(
        "spark.ingestion.parsers.pdf_parser._extract_table_objects",
        lambda _path, _count: [],
    )

    async def fake_apply(_path, pages, _cfg):
        return (
            [
                (1, pages[0][1], "pypdf", None),
                (2, "OCR recovered page two", "ocr", 90.0),
            ],
            {"ocr_page_count": 1, "ocr_char_count": 22, "ocr_confidence_min": 90.0},
        )

    monkeypatch.setattr(
        "spark.ingestion.parsers.pdf_parser._apply_per_page_ocr_async",
        fake_apply,
    )
    parser = PDFParser()
    records = [rec async for rec in parser.parse(Path("mixed.pdf"), {})]

    assert len(records) == 2
    combined = " ".join(rec.payload["page_content"] for rec in records)
    assert "Digital overview" in combined
    assert "OCR recovered page two" in combined


@pytest.mark.asyncio
async def test_resolve_ingest_generation_first_ingest() -> None:
    session = AsyncMock()
    session.get.return_value = None
    session.scalar.return_value = 0

    plan = await resolve_ingest_generation(session, uuid.uuid4())

    assert plan == IngestGenerationPlan(staging=1, active=0, is_reingest=False)


@pytest.mark.asyncio
async def test_resolve_ingest_generation_reingest_increments() -> None:
    session = AsyncMock()
    doc = MagicMock()
    doc.active_ingest_generation = 2
    doc.chunks_count = 4
    session.get.return_value = doc
    session.scalar.return_value = 4

    plan = await resolve_ingest_generation(session, uuid.uuid4())

    assert plan == IngestGenerationPlan(staging=3, active=2, is_reingest=True)
