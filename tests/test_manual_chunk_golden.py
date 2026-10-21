"""Golden chunk boundary fixtures for industrial document types."""

from __future__ import annotations

from pathlib import Path

from spark.ingestion.chunk.registry import chunk_text_leaves

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "manuals"


def test_manual_fixture_preserves_section_path() -> None:
    text = (FIXTURES / "cooling_fan_section.txt").read_text(encoding="utf-8")
    leaves = chunk_text_leaves(
        text,
        strategy="parent_child",
        parent_chunk_size=800,
        parent_chunk_overlap=0,
        child_chunk_size=200,
        child_chunk_overlap=0,
    )
    assert leaves
    assert any("Cooling System" in (leaf.section_path or "") for leaf in leaves)
    assert any("SKF-6205" in leaf.text for leaf in leaves)


def test_sop_procedure_splits_on_thai_step_heading() -> None:
    text = (
        "ขั้นตอนที่ 1 ตรวจสอบสวิตช์\n"
        "เปิดแผงควบคุมและวัดแรงดัน\n\n"
        "ขั้นตอนที่ 2 ทดสอบมอเตอร์\n"
        "หมุนมอเตอร์ด้วยมือและฟังเสียง\n"
    )
    from spark.ingestion.chunk.registry import chunk_text

    chunks = chunk_text(text, strategy="sop_procedure", chunk_size=500, chunk_overlap=0)
    assert len(chunks) >= 2

