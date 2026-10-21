"""Phase 4 — parse/chunk/embed quality (parent-child, tables, semantic, OCR)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spark.ingestion.chunk.registry import chunk_text, chunk_text_leaves
from spark.ingestion.chunk.semantic import split_by_embedding_breakpoint
from spark.ingestion.ocr_quality import OCRQualityTracker
from spark.ingestion.parse.table_object import TableObject, table_rows_to_markdown
from spark.workers.celery_app import celery_app


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingest"


def test_parent_child_section_path_in_payload() -> None:
    text = (FIXTURES / "manual_with_sections.txt").read_text(encoding="utf-8")
    leaves = chunk_text_leaves(
        text,
        strategy="parent_child",
        parent_chunk_size=800,
        parent_chunk_overlap=0,
        child_chunk_size=200,
        child_chunk_overlap=0,
    )
    assert leaves
    paths = [leaf.section_path for leaf in leaves if leaf.section_path]
    assert paths
    assert any("Cooling System" in p for p in paths)


def test_table_object_part_number_payload() -> None:
    markdown = table_rows_to_markdown(
        [
            ["Part", "Torque"],
            ["PN-8842", "25 Nm"],
            ["PN-8843", "45 Nm"],
        ]
    )
    table = TableObject(
        markdown=markdown,
        headers=["Part", "Torque"],
        rows=[{"Part": "PN-8842", "Torque": "25 Nm"}, {"Part": "PN-8843", "Torque": "45 Nm"}],
        page=3,
    )
    payload = table.to_payload()
    assert "PN-8842" in payload["part_numbers"]
    assert "PN-8842" in table.to_embed_text()


def test_semantic_fewer_mid_sentence_splits_than_recursive() -> None:
    text = (
        "The servo amplifier monitors motor temperature continuously. "
        "When the threshold is exceeded the drive enters safe mode. "
        "Operators must verify cooling fans before restart. "
        "Document revision R3 applies to MC-500 series machines."
    )
    recursive = chunk_text(text, strategy="recursive", chunk_size=80, chunk_overlap=0)
    semantic = split_by_embedding_breakpoint(
        text,
        chunk_size=80,
        chunk_overlap=0,
        breakpoint_threshold=0.5,
    )
    recursive_mid = sum(1 for c in recursive if c and c[0].islower())
    semantic_mid = sum(1 for c in semantic if c and c[0].islower())
    assert len(semantic) >= 1
    assert semantic_mid <= recursive_mid


def test_ocr_task_routes_to_ocr_heavy_queue() -> None:
    routes = celery_app.conf.task_routes or {}
    assert routes.get("spark.workers.tasks_ocr.*") == {"queue": "ocr_heavy"}


def test_safety_manual_40_percent_bad_ocr_blocks_tags_not_fails() -> None:
    tracker = OCRQualityTracker()
    for i in range(10):
        conf = 40.0 if i < 4 else 85.0
        tracker.add_block(i + 1, "ocr", conf, block_index=i)
    detail = tracker.enforce_job_quality(document_type="machine_manual", total_page_count=10)
    assert detail is not None


def test_safety_manual_20_percent_bad_ocr_blocks_passes() -> None:
    tracker = OCRQualityTracker()
    for i in range(10):
        conf = 40.0 if i < 2 else 85.0
        tracker.add_block(i + 1, "ocr", conf, block_index=i)
    tracker.enforce_job_quality(document_type="machine_manual", total_page_count=10)


@pytest.mark.asyncio
async def test_pdf_parser_async_ocr_enqueues_heavy_queue(tmp_path: Path) -> None:
    from spark.ingestion.parsers.pdf_parser import _run_ocr_pages_async

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    mock_result = MagicMock()
    mock_result.ready.return_value = True
    mock_result.get.return_value = {
        "pages": [
            {"page_number": 1, "text": "ocr text", "confidence": 88.0},
            {"page_number": 2, "text": "more text", "confidence": 90.0},
        ]
    }
    mock_task = MagicMock()
    mock_task.apply_async.return_value = mock_result

    with patch("spark.workers.tasks_ocr.ocr_pdf_pages_task", mock_task):
        with patch("spark.ingestion.parsers.pdf_parser.settings") as mock_settings:
            mock_settings.spark_profile = "production"
            mock_settings.spark_testing = False
            pages = await _run_ocr_pages_async(
                pdf,
                [1, 2],
                {"async": True, "async_page_threshold": 2, "lang": "eng", "async_timeout": 30},
            )
    mock_task.apply_async.assert_called_once()
    assert mock_task.apply_async.call_args.kwargs.get("queue") == "ocr_heavy"
    assert 1 in pages and pages[1].text == "ocr text"
