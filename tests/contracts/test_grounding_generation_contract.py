"""Contract: Phase 10 grounding and generation hardening."""

from __future__ import annotations


def test_phase10_generation_package_exports() -> None:
    from spark.generation import (
        generate,
        grounded_generate_with_enforced_citations,
        select_evidence_spans,
        validate_grounded_citations,
        validate_spans_grounded,
    )
    from spark.generation.numeric import answer_numerics_subset_of_context, extract_numerics
    from spark.generation.types import GenerationInput, GenerationOutput

    assert callable(generate)
    assert callable(grounded_generate_with_enforced_citations)
    assert callable(select_evidence_spans)
    assert callable(validate_spans_grounded)
    assert callable(validate_grounded_citations)
    assert callable(extract_numerics)
    assert callable(answer_numerics_subset_of_context)
    assert GenerationInput is not None
    assert GenerationOutput is not None


def test_canonical_generation_import_paths() -> None:
    from spark.generation.evidence_spans import select_evidence_spans
    from spark.generation.pipeline import extract_then_generate
    from spark.generation.pipeline import grounded_generate_with_enforced_citations
    from spark.generation.numeric import extract_numerics

    assert callable(select_evidence_spans)
    assert callable(extract_then_generate)
    assert callable(grounded_generate_with_enforced_citations)
    assert callable(extract_numerics)


def test_source_span_schema() -> None:
    from spark.schemas.rag import SourceRef, SourceSpan

    ref = SourceRef(
        score=0.9,
        spans=[SourceSpan(chunk_id="abc", start_offset=0, end_offset=12, text="LOTO step")],
    )
    assert ref.spans[0].start_offset == 0


def test_generation_prompts_v2_exists() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "configs" / "generation" / "prompts_v2.yaml"
    assert path.is_file()
