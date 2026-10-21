"""Unified grounded generation package (Phase 10)."""

from spark.generation.citations import CHUNK_CITATION_RE, validate_grounded_citations
from spark.generation.context import (
    append_readable_citations,
    build_grounded_context,
    is_machine_anchored,
    llm_prompt_payload,
)
from spark.generation.evidence_spans import (
    EvidenceSpan,
    format_extractive_with_citations,
    select_evidence_spans,
    validate_spans_grounded,
)
from spark.generation.extractive import format_extractive_answer
from spark.generation.numeric import answer_numerics_subset_of_context, extract_numerics
from spark.generation.pipeline import (
    build_generation_input,
    extract_then_generate,
    generate,
    grounded_generate_with_enforced_citations,
)
from spark.generation.streaming import StreamEvent, stream_generation, stream_grounded_answer
from spark.generation.types import GenerationInput, GenerationOutput, GroundedGenerateResult

__all__ = [
    "CHUNK_CITATION_RE",
    "EvidenceSpan",
    "GenerationInput",
    "GenerationOutput",
    "GroundedGenerateResult",
    "answer_numerics_subset_of_context",
    "append_readable_citations",
    "build_grounded_context",
    "extract_numerics",
    "build_generation_input",
    "extract_then_generate",
    "format_extractive_answer",
    "format_extractive_with_citations",
    "generate",
    "grounded_generate_with_enforced_citations",
    "is_machine_anchored",
    "llm_prompt_payload",
    "select_evidence_spans",
    "stream_generation",
    "stream_grounded_answer",
    "StreamEvent",
    "validate_grounded_citations",
    "validate_spans_grounded",
]
