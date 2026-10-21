"""Phase 6 — SOP procedure step chunking with LOTO and safety blocks."""

from __future__ import annotations

from pathlib import Path

from spark.ingestion.chunk.sop_procedure import SopProcedureChunker, split_sop_leaves, split_sop_segments
from spark.ingestion.chunk.strategies import StructureAwareChunker
from spark.ingestion.chunking.structure import split_structure_aware

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parsing"

SOP_WITH_SAFETY = """
Standard Operating Procedure — Spindle Bearing Service

LOTO: Turn off main power at panel A. Apply lock and tag before service.

WARNING: Hot surfaces may cause burns. Allow 15 minutes cooldown.

1. Verify the machine is in maintenance mode.

2. Locate the grease fitting on the main spindle bearing.

3. Apply NLGI Grade 2 grease until clean grease appears at the relief port.
""".strip()


def test_sop_fixture_splits_loto_warning_and_steps() -> None:
    segments = split_sop_segments(SOP_WITH_SAFETY)
    block_types = {segment.block_type for segment in segments}
    assert "loto" in block_types
    assert "warning" in block_types
    assert "sop_step" in block_types
    step_segments = [segment for segment in segments if segment.block_type == "sop_step"]
    assert len(step_segments) >= 3
    assert step_segments[0].step_index == 1
    assert any("grease fitting" in segment.text for segment in step_segments)


def test_sop_leaves_carry_step_metadata() -> None:
    leaves = split_sop_leaves(SOP_WITH_SAFETY, chunk_size=800, chunk_overlap=50)
    loto = [leaf for leaf in leaves if leaf.block_type == "loto"]
    steps = [leaf for leaf in leaves if leaf.block_type == "sop_step"]
    assert loto and "LOTO" in loto[0].text
    assert steps and steps[0].step_index == 1


def test_sop_procedure_differs_from_structure_aware() -> None:
    sop_chunks = SopProcedureChunker().split(SOP_WITH_SAFETY, chunk_size=500, chunk_overlap=50)
    structure_chunks = StructureAwareChunker().split(SOP_WITH_SAFETY, chunk_size=500, chunk_overlap=50)
    assert sop_chunks != structure_chunks
    assert any("LOTO" in chunk for chunk in sop_chunks)
    assert not any(chunk.strip().startswith("LOTO") for chunk in structure_chunks)


def test_word_sop_fixture_has_discrete_steps() -> None:
    text = (FIXTURES / "word_sop_procedure.txt").read_text(encoding="utf-8")
    segments = split_sop_segments(text)
    assert sum(1 for segment in segments if segment.block_type == "sop_step") >= 5


def test_structure_aware_still_splits_numbered_steps() -> None:
    text = (FIXTURES / "word_sop_procedure.txt").read_text(encoding="utf-8")
    chunks = split_structure_aware(text, chunk_size=500, chunk_overlap=50)
    assert len(chunks) >= 3
