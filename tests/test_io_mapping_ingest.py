"""IO-mapping ingestion: bilateral Excel header, content-signature detection."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from spark.ingestion.config_loader import load_config
from spark.ingestion.document_type_resolver import resolve_document_type
from spark.ingestion.parsers.excel_parser import ExcelParser


def _write_bilateral_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Symlinks"
    ws.append(["Symbolic Link Name", None, None, None, "Connected to (Hardware Ports)", None, None, None, None])
    ws.append(["Device", "Type", "Direction", "Path", "Device", "Type", "Direction", "Path", "Comment"])
    ws.append(["EcoRT_0", "BOOL", "Input", "RES0.BELT_CALIB_SENSOR", None, None, None, None, None])
    ws.append(
        [
            "EcoRT_0",
            "INT",
            "Input",
            "RES0.Belt_Control",
            "EcoRT_0",
            "INT",
            "Output",
            "RES0.MODBUSRREG8_Operation_Control_3_10.r2LinkName",
            "Names a Read Symbolic link variable",
        ]
    )
    wb.save(path)


@pytest.fixture
def bilateral_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "some_export.xlsx"
    _write_bilateral_workbook(path)
    return path


def test_resolve_document_type_filename_hint() -> None:
    assert resolve_document_type("MAPPING.xlsx") == "io_mapping"
    assert resolve_document_type("mapping_diagram.pdf") == "io_mapping"


def test_resolve_document_type_content_signature_regardless_of_filename(bilateral_xlsx: Path) -> None:
    content = bilateral_xlsx.read_bytes()
    resolved = resolve_document_type("random_export_2026.xlsx", content=content)
    assert resolved == "io_mapping"


async def test_excel_parser_bilateral_rows_clean_narrative(bilateral_xlsx: Path) -> None:
    cfg = load_config("io_mapping")
    records = [rec async for rec in ExcelParser().parse(bilateral_xlsx, cfg)]

    assert len(records) == 2
    contents = [r.payload["page_content"] for r in records]

    one_sided = next(c for c in contents if "BELT_CALIB_SENSOR" in c)
    assert "None" not in one_sided
    assert "no mapped target in this sheet" in one_sided

    two_sided = next(c for c in contents if "MODBUSRREG8" in c)
    assert "None" not in two_sided
    assert "connects to EcoRT_0 (INT, Output) at RES0.MODBUSRREG8" in two_sided
    assert "Names a Read Symbolic link variable" in two_sided


async def test_excel_parser_row_number_matches_spreadsheet(bilateral_xlsx: Path) -> None:
    """Citations show row numbers to users cross-checking in Excel — with the
    header on sheet row 2 (header_row: 1), the first data row is sheet row 3."""
    cfg = load_config("io_mapping")
    records = [rec async for rec in ExcelParser().parse(bilateral_xlsx, cfg)]
    assert [r.payload["row_number"] for r in records] == [3, 4]


async def test_excel_parser_tgt_only_row_gets_port_narrative(tmp_path: Path) -> None:
    """473 of 854 rows in the real sheet have only the hardware-port half —
    they must not render as '(, ) at  connects to ...'."""
    path = tmp_path / "tgt_only.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Symlinks"
    ws.append(["Symbolic Link Name", None, None, None, "Connected to (Hardware Ports)", None, None, None, None])
    ws.append(["Device", "Type", "Direction", "Path", "Device", "Type", "Direction", "Path", "Comment"])
    ws.append([None, None, None, None, "EcoRT_0", "VTQWORD", "Output", "RES0.SERVO_PEEL_D1.Fixation_I_O_OUT", None])
    ws.append([None, None, None, None, None, None, None, None, None])  # spacer row
    wb.save(path)

    cfg = load_config("io_mapping")
    records = [rec async for rec in ExcelParser().parse(path, cfg)]

    assert len(records) == 1  # spacer row skipped entirely
    content = records[0].payload["page_content"]
    assert not content.startswith("(")
    assert "No symbolic link mapped in this row" in content
    assert "RES0.SERVO_PEEL_D1.Fixation_I_O_OUT" in content
    assert records[0].payload.get("tgt_path") == "RES0.SERVO_PEEL_D1.Fixation_I_O_OUT"
    assert (records[0].text_for_embedding or "").strip()


async def test_excel_parser_carries_exact_match_tag_fields(bilateral_xlsx: Path) -> None:
    cfg = load_config("io_mapping")
    records = [rec async for rec in ExcelParser().parse(bilateral_xlsx, cfg)]
    two_sided = next(r for r in records if r.payload.get("tgt_path"))
    assert two_sided.payload["src_path"] == "RES0.Belt_Control"
    assert two_sided.payload["tgt_path"] == "RES0.MODBUSRREG8_Operation_Control_3_10.r2LinkName"


def test_writer_normalizes_tag_paths_for_case_insensitive_lookup() -> None:
    """QdrantWriter lowercases src_path/tgt_path so the exact-tag filter (which
    lowercases the query-side tag) matches regardless of how the sheet or the
    technician cased it."""
    from spark.ingestion.index.qdrant_writer import _normalized_tag_path

    assert _normalized_tag_path("RES0.Belt_Control") == "res0.belt_control"
    assert _normalized_tag_path("  RES0.X  ") == "res0.x"
    assert _normalized_tag_path(None) is None
    assert _normalized_tag_path("") is None
