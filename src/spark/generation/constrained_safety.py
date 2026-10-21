"""Structured safety generation with per-step citation validation (Phase 10).

Remediation v4: every safety step must have individual grounded citation.
"""

from __future__ import annotations

import json
import re

from spark.core.logging import get_logger
from spark.generation.citations import validate_structured_safety_citations
from spark.generation.context import append_readable_citations, build_grounded_context, chunk_id_map
from spark.generation.parent_context import generation_context_for_doc
from spark.generation.schemas.safety_answer import SafetyAnswerSchema
from spark.generation.types import GenerationInput, GroundedGenerateResult
from spark.generation.usage import record_llm_usage, summarize_llm_usage
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent
from spark.retrieval.constants import NO_DATA_ANSWER

log = get_logger(__name__)


def intent_requires_structured_safety(question: str) -> bool:
    return detect_safety_intent(question).kind != SafetyIntentKind.NONE


def format_safety_answer(schema: SafetyAnswerSchema) -> str:
    lines: list[str] = []
    for index, step in enumerate(schema.steps, start=1):
        lines.append(f"{index}. {step.strip()}")
    if schema.warnings:
        lines.append("")
        lines.append("คำเตือน:")
        for warning in schema.warnings:
            lines.append(f"- {warning.strip()}")
    return "\n".join(lines).strip()


async def _invoke_structured_schema(inp: GenerationInput, prompt: str) -> SafetyAnswerSchema | None:
    structured_fn = getattr(inp.llm, "with_structured_output", None)
    if callable(structured_fn):
        try:
            runnable = structured_fn(SafetyAnswerSchema)
            result = await runnable.ainvoke(prompt)
            record_llm_usage(inp, result, llm=inp.llm, operation="structured_safety")
            if isinstance(result, SafetyAnswerSchema):
                return result
            return SafetyAnswerSchema.model_validate(result)
        except Exception as exc:
            log.warning("constrained_safety_structured_output_failed", error=str(exc)[:200])
            return None

    try:
        response = await inp.llm.ainvoke(prompt)
        record_llm_usage(inp, response, llm=inp.llm, operation="structured_safety")
        raw = response.content if hasattr(response, "content") else str(response)
        text = str(raw or "").strip()
        if not text:
            return None
        return SafetyAnswerSchema.model_validate(json.loads(text))
    except Exception as exc:
        log.warning("constrained_safety_json_parse_failed", error=str(exc)[:200])
        return None


def _attach_chunk_citations(answer: str, schema: SafetyAnswerSchema) -> str:
    if not schema.citations:
        return answer
    suffix = " ".join(f"[chunk_id:{ref.chunk_id}]" for ref in schema.citations)
    return f"{answer}\n\n{suffix}".strip()


async def run_constrained_safety(inp: GenerationInput) -> GroundedGenerateResult:
    """Generate a schema-validated safety answer through grounded LLM output."""
    if not inp.docs:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    context = build_grounded_context(inp.docs)
    if not context.strip():
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    prompt = (
        "Return JSON matching SafetyAnswerSchema with steps, warnings, citations, confidence.\n"
        "CRITICAL: Every step MUST be directly supported by text in the context. "
        "Each citation must reference a valid chunk_id from the context. "
        "Steps without evidence in the context MUST NOT be included.\n\n"
        f"Context:\n{context}\n\nQuestion:\n{inp.question}\n"
    )

    schema = await _invoke_structured_schema(inp, prompt)
    if schema is None or not schema.steps:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    valid, cited_docs = validate_structured_safety_citations(schema, inp.docs)
    if not valid:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    uncited_steps = _find_uncited_steps(schema, inp.docs)
    if uncited_steps:
        log.warning(
            "constrained_safety_uncited_steps",
            uncited_count=len(uncited_steps),
            total_steps=len(schema.steps),
            uncited_indices=uncited_steps[:5],
        )
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="safety_step_ungrounded",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    answer = append_readable_citations(
        _attach_chunk_citations(format_safety_answer(schema), schema),
        cited_docs,
    )
    return GroundedGenerateResult(
        answer=answer,
        cited_docs=cited_docs,
        answer_path="grounded_structured_safety",
        citations_verified=True,
        generation_mode="grounded_llm",
        llm_usage=summarize_llm_usage(inp.llm_usage_calls),
    )


def _find_uncited_steps(
    schema: SafetyAnswerSchema,
    docs: list[RetrievedDoc],
) -> list[int]:
    """Return indices of steps that lack grounding evidence in any cited document."""
    if not schema.citations:
        return list(range(len(schema.steps)))

    id_map = chunk_id_map(docs)
    cited_docs: list[RetrievedDoc] = []
    for ref in schema.citations:
        doc = id_map.get(ref.chunk_id.strip().lower())
        if doc is not None and doc not in cited_docs:
            cited_docs.append(doc)

    if not cited_docs:
        return list(range(len(schema.steps)))

    combined_context = "\n".join(generation_context_for_doc(doc) for doc in cited_docs).lower()
    context_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", combined_context))

    uncited: list[int] = []
    for i, step_text in enumerate(schema.steps):
        step_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", step_text.lower()))
        if not step_tokens:
            continue
        overlap = len(step_tokens & context_tokens) / len(step_tokens)
        if overlap < 0.35:
            uncited.append(i)
    return uncited
