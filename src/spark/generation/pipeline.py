"""Generation pipeline — grounded LLM answer path."""

from __future__ import annotations

import inspect

from spark.core.logging import get_logger
from spark.generation.constrained_safety import intent_requires_structured_safety, run_constrained_safety
from spark.generation.context import build_grounded_context
from spark.generation.grounded_llm import run_grounded_llm
from spark.generation.nli_gate import apply_nli_gate
from spark.generation.policy import GenerationPolicy
from spark.retrieval.deadline import RequestDeadline
from spark.generation.types import GenerationInput, GenerationOutput, GroundedGenerateResult
from spark.retrieval.constants import NO_DATA_ANSWER

log = get_logger(__name__)


async def _apply_nli_gate(question: str, result: GroundedGenerateResult, *, context: str) -> GroundedGenerateResult:
    gated = apply_nli_gate(question, result, context=context)
    if inspect.isawaitable(gated):
        return await gated
    return gated


def build_generation_input(
    *,
    question: str,
    docs,
    llm,
    chat_history=None,
    synthesis_question: str | None = None,
    extractive_first: bool | None = None,
    policy: GenerationPolicy | None = None,
    deadline: RequestDeadline | None = None,
    prompt_template=None,
) -> GenerationInput:
    inp = GenerationInput(
        question=question,
        docs=docs,
        llm=llm,
        chat_history=chat_history,
        synthesis_question=synthesis_question,
    )
    if extractive_first is not None:
        inp.force_extractive_first = extractive_first
    elif policy is not None:
        inp.force_extractive_first = policy.force_extractive(question)
    if deadline is not None:
        inp.deadline = deadline
    if prompt_template is not None:
        inp.prompt_template = prompt_template
    return inp


async def generate(inp: GenerationInput) -> GenerationOutput:
    from spark.observability.otel_tracing import record_span_event, start_span

    if not inp.docs:
        empty = GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
        return GenerationOutput(result=empty)

    with start_span("rag.generate", doc_count=len(inp.docs)) as gen_span:
        context = build_grounded_context(inp.docs)

        if intent_requires_structured_safety(inp.question):
            with start_span("rag.generate.constrained_safety"):
                structured = await run_constrained_safety(inp)
            if structured.citations_verified:
                with start_span("rag.generate.nli_gate"):
                    structured = await _apply_nli_gate(inp.question, structured, context=context)
                record_span_event(gen_span, "generation_complete", mode=structured.generation_mode, answer_path=structured.answer_path)
                log.info("generation_complete", mode=structured.generation_mode, answer_path=structured.answer_path)
                return GenerationOutput(result=structured, spans_used=len(structured.cited_docs))

        with start_span("rag.generate.crag_verify"):
            from spark.retrieval.safety.retrieval_verifier import verify_retrieval
            from spark.retrieval.safety.safety_intent import detect_safety_intent as _detect_safety
            from spark.retrieval.safety.safety_intent import SafetyIntentKind
            _crag_safety = _detect_safety(inp.question)
            crag = await verify_retrieval(
                inp.question, inp.docs,
                use_llm=_crag_safety.kind != SafetyIntentKind.NONE,
            )
            if crag.action == "reject":
                log.info("crag_reject_softened", doc_count=len(inp.docs))
            # Narrow to CRAG-approved docs only for safety questions (LLM-judged).
            # The non-safety heuristic scores by raw token overlap, which is ~0
            # for Thai questions over English manuals — narrowing there dropped
            # the doc holding the answer and produced false "not documented".
            if (
                crag.action == "accept"
                and crag.relevant_docs
                and _crag_safety.kind != SafetyIntentKind.NONE
            ):
                inp.docs = crag.relevant_docs

        with start_span("rag.generate.grounded_llm"):
            result = await run_grounded_llm(inp)
        with start_span("rag.generate.nli_gate"):
            result = await _apply_nli_gate(inp.question, result, context=context)

        with start_span("rag.generate.self_verify"):
            from spark.generation.self_verify import self_verify_answer
            verify_result = await self_verify_answer(inp.question, result, inp.docs)
            if (
                verify_result.needs_correction
                and result.answer_path != "nli_gate_fail"
                # An answer that already failed a gate went through
                # flag_or_suppress inside run_grounded_llm and carries the
                # unverified warning; re-flagging it here only stacks a
                # duplicate suffix (or resummarizes an already-flagged answer).
                and result.citations_verified
            ):
                log.info(
                    "self_verify_low_confidence",
                    score=verify_result.verification_score,
                    correction_queries=verify_result.correction_queries[:2],
                    citations_verified=result.citations_verified,
                )
                from spark.generation.unverified import flag_or_suppress

                result = await flag_or_suppress(
                    result.answer,
                    inp.docs,
                    is_safety=False,
                    reason="self_verify_correction_unavailable",
                    llm=inp.llm,
                    question=inp.question,
                    chat_history=inp.chat_history,
                )

        record_span_event(gen_span, "generation_complete", mode=result.generation_mode, answer_path=result.answer_path)
        log.info("generation_complete", mode=result.generation_mode, answer_path=result.answer_path)
        return GenerationOutput(result=result)


async def grounded_generate_with_enforced_citations(
    *,
    question: str,
    docs,
    llm,
    chat_history=None,
    synthesis_question: str | None = None,
    extractive_first: bool | None = None,
    policy: GenerationPolicy | None = None,
    deadline: RequestDeadline | None = None,
    prompt_template=None,
) -> GroundedGenerateResult:
    """Backward-compatible entry used by RAGService."""
    inp = build_generation_input(
        question=question,
        docs=docs,
        llm=llm,
        chat_history=chat_history,
        synthesis_question=synthesis_question,
        extractive_first=extractive_first,
        policy=policy,
        deadline=deadline,
        prompt_template=prompt_template,
    )
    return (await generate(inp)).result


async def extract_then_generate(
    *,
    question: str,
    docs,
    llm,
    chat_history=None,
    synthesis_question: str | None = None,
    extractive_first: bool | None = None,
    policy: GenerationPolicy | None = None,
    deadline: RequestDeadline | None = None,
) -> GroundedGenerateResult:
    return await grounded_generate_with_enforced_citations(
        question=question,
        docs=docs,
        llm=llm,
        chat_history=chat_history,
        synthesis_question=synthesis_question,
        extractive_first=extractive_first,
        policy=policy,
        deadline=deadline,
    )
