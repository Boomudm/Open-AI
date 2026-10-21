"""Grounded LLM generation with citation enforcement (Phase 10)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.production_profile import ProductionProfile
from spark.generation.citations import citation_validation_failure, validate_grounded_citations
from spark.generation.context import append_readable_citations, build_grounded_context, llm_prompt_payload
from spark.generation.thai_enforce import answer_fails_thai_policy, thai_retry_addendum
from spark.generation.types import GenerationInput, GroundedGenerateResult
from spark.generation.usage import record_llm_usage, summarize_llm_usage
from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER
from spark.retrieval.scoring import _is_off_topic_factory_question

log = get_logger(__name__)


def _effective_llm_timeout_sec(deadline: Any | None) -> float:
    base = float(settings.rag_llm_timeout_sec or 60)
    if deadline is None:
        return base
    from spark.retrieval.deadline import RequestDeadline

    if not isinstance(deadline, RequestDeadline):
        return base
    remaining_sec = max(0.001, deadline.remaining_ms() / 1000.0)
    return min(base, remaining_sec)


# A real answer body is longer than this; below it (with no citation) the reply
# is a transport/decoder artifact, not content — e.g. the KKU gateway was
# observed returning a 3-token reply over full evidence.
_DEGENERATE_ANSWER_MAX_CHARS = 40


def _generation_retry_reason(answer: str | None) -> str | None:
    """Triage a completed (non-timeout) LLM reply for the single regenerate call.

    Returns the reason to retry, or None to accept the reply. Retry-worthy
    replies are ones where the model did not actually engage with the evidence:
    empty, degenerate (a few uncited tokens), or a bare refusal. The same
    context has been observed producing a grounded answer on the next attempt
    (gateway non-determinism), so one more call is cheaper than serving a false
    no_data after already paying for retrieval + rerank.
    """
    text = (answer or "").strip()
    if not text:
        return "empty_response"
    if "[chunk_id:" not in text.lower() and len(text) <= _DEGENERATE_ANSWER_MAX_CHARS:
        return "degenerate_response"
    from spark.generation.unverified import _is_refusal_only

    if _is_refusal_only(text):
        return "refusal_only"
    return None


async def _retry_thai_grounded_llm(
    *,
    llm: Any,
    question: str,
    context: str,
    chat_history: list[tuple[str, str]] | None,
) -> str | None:
    from spark.generation.prompts import rag_prompt

    payload = llm_prompt_payload(
        context=context,
        question=f"{question}\n\n{thai_retry_addendum()}",
        chat_history=chat_history,
    )
    try:
        formatted = await rag_prompt.ainvoke(payload)
        response = await asyncio.wait_for(
            llm.ainvoke(formatted),
            timeout=_effective_llm_timeout_sec(None),
        )
        raw = response.content if hasattr(response, "content") else str(response)
        return str(raw or "").strip() or None
    except Exception as exc:
        log.warning("grounded_generate_thai_retry_failed", error=str(exc)[:200])
        return None


async def run_grounded_llm(inp: GenerationInput) -> GroundedGenerateResult:
    context = build_grounded_context(inp.docs)
    if not context.strip():
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )

    from spark.generation.prompts import rag_prompt

    active_prompt = inp.prompt_template if inp.prompt_template is not None else rag_prompt
    prompt_question = inp.synthesis_question or inp.question
    payload = llm_prompt_payload(
        context=context,
        question=prompt_question,
        chat_history=inp.chat_history,
    )

    answer: str | None = None
    answer_path = "grounded_llm"
    try:
        formatted = await active_prompt.ainvoke(payload)
        total_budget = _effective_llm_timeout_sec(inp.deadline)
        first_timeout = total_budget
        if settings.rag_generation_retry_enabled and total_budget >= 60.0:
            first_timeout = min(total_budget, float(settings.rag_llm_hedge_timeout_sec))
        # Hedged attempts: the gateway stalls whole requests
        # non-deterministically (observed 1 in 6, and back-to-back stalls do
        # happen — 17-18 Jul live runs lost asks to TWO consecutive stalls),
        # while a healthy call lands in ~5-19s. Every non-final attempt is
        # capped at the hedge timeout so a stall costs 25s, not the budget;
        # the final attempt gets whatever budget remains. Intermediate stalls
        # are deliberately NOT recorded as llm_timeout: the circuit breaker
        # should trip on requests that actually failed, not on hedged stalls
        # that recovered.
        hedged = first_timeout < total_budget
        max_attempts = 3 if hedged else 1
        started_at = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            remaining = (
                _effective_llm_timeout_sec(inp.deadline)
                if inp.deadline is not None
                else max(5.0, total_budget - (time.monotonic() - started_at))
            )
            hedge_cap = float(settings.rag_llm_hedge_timeout_sec)
            is_final = attempt >= max_attempts or remaining <= hedge_cap + 5.0
            attempt_timeout = remaining if is_final else min(remaining, hedge_cap)
            try:
                response = await asyncio.wait_for(
                    inp.llm.ainvoke(formatted),
                    timeout=attempt_timeout,
                )
                break
            except Exception as attempt_exc:
                if is_final:
                    raise
                log.warning(
                    "grounded_llm_first_attempt_stalled",
                    attempt=attempt,
                    error=f"{type(attempt_exc).__name__}: {str(attempt_exc)[:120]}",
                    first_timeout_sec=attempt_timeout,
                )
        record_llm_usage(inp, response, llm=inp.llm, operation="grounded_llm")
        raw = response.content if hasattr(response, "content") else str(response)
        answer = str(raw or "").strip()
    except TimeoutError:
        log.error("rag_llm_timeout", timeout=settings.rag_llm_timeout_sec)
        answer_path = "llm_unavailable"
        try:
            from spark.retrieval.safety.circuit_breaker import record_rag_outcome

            record_rag_outcome(
                "llm_timeout",
                enabled=ProductionProfile.from_settings().rag_circuit_enabled,
            )
        except Exception:
            pass
    except Exception as exc:
        log.error("rag_llm_failed", error=str(exc)[:500])
        answer_path = "llm_unavailable"

    retry_reason = (
        _generation_retry_reason(answer)
        if answer_path == "grounded_llm" and settings.rag_generation_retry_enabled
        else None
    )
    if retry_reason and _effective_llm_timeout_sec(inp.deadline) >= 5.0:
        log.info(
            "grounded_llm_regenerate",
            reason=retry_reason,
            first_preview=(answer or "")[:80],
        )
        try:
            response = await asyncio.wait_for(
                inp.llm.ainvoke(formatted),
                timeout=_effective_llm_timeout_sec(inp.deadline),
            )
            record_llm_usage(inp, response, llm=inp.llm, operation="grounded_llm_retry")
            raw = response.content if hasattr(response, "content") else str(response)
            second = str(raw or "").strip()
            # Adopt the retry only when it engaged with the evidence; a repeated
            # refusal keeps the original so no_data handling stays honest.
            if second and _generation_retry_reason(second) is None:
                answer = second
        except Exception as exc:
            log.warning("grounded_llm_regenerate_failed", error=str(exc)[:200])

    if answer:
        log.debug(
            "grounded_llm_raw_answer",
            answer_preview=answer[:300],
            has_chunk_id="[chunk_id:" in answer.lower(),
        )
        valid, cited_docs = validate_grounded_citations(answer, inp.docs, question=inp.question)
        if valid:
            if answer_fails_thai_policy(inp.question, answer):
                retry = await _retry_thai_grounded_llm(
                    llm=inp.llm,
                    question=prompt_question,
                    context=context,
                    chat_history=inp.chat_history,
                )
                if retry:
                    valid_retry, cited_retry = validate_grounded_citations(retry, inp.docs, question=inp.question)
                    if valid_retry and not answer_fails_thai_policy(inp.question, retry):
                        return replace(GroundedGenerateResult(
                            answer=append_readable_citations(retry, cited_retry),
                            cited_docs=cited_retry,
                            answer_path="grounded_llm",
                            citations_verified=True,
                            generation_mode="grounded_llm",
                        ), llm_usage=summarize_llm_usage(inp.llm_usage_calls))
                from spark.generation.unverified import flag_or_suppress

                final = await flag_or_suppress(
                    answer,
                    inp.docs,
                    is_safety=False,
                    reason="thai_policy_incomplete",
                    llm=inp.llm,
                    question=inp.question,
                    chat_history=inp.chat_history,
                )
                return replace(final, llm_usage=summarize_llm_usage(inp.llm_usage_calls))

            return replace(GroundedGenerateResult(
                answer=append_readable_citations(answer, cited_docs),
                cited_docs=cited_docs,
                answer_path=answer_path,
                citations_verified=True,
                generation_mode="grounded_llm",
            ), llm_usage=summarize_llm_usage(inp.llm_usage_calls))

        failure = citation_validation_failure(answer, inp.docs, question=inp.question)
        if failure == "numeric_grounding_fail":
            from spark.audit.worm_sink import schedule_worm_audit

            schedule_worm_audit(
                "numeric_grounding_fail",
                payload={
                    "question": inp.question[:400],
                    "answer_preview": answer[:400],
                },
            )
            # A number that contradicts the cited evidence is a fabrication —
            # the one failure mode that must NEVER be shown, even flagged. All
            # other gate misses fall through to flag-don't-suppress below.
            log.info("grounded_generate_numeric_fail_suppressed", question=inp.question[:120])
            return GroundedGenerateResult(
                answer=NO_DATA_ANSWER,
                cited_docs=[],
                answer_path="numeric_grounding_fail",
                citations_verified=False,
                generation_mode="no_data",
                llm_usage=summarize_llm_usage(inp.llm_usage_calls),
            )
        log.info(
            "grounded_generate_validation_warning",
            reason=failure or "citation_validation_failed",
            question=inp.question[:120],
        )
        from spark.generation.unverified import flag_or_suppress

        final = await flag_or_suppress(
            answer,
            inp.docs,
            is_safety=False,
            reason=failure or "citation_incomplete",
            llm=inp.llm,
            question=inp.question,
            chat_history=inp.chat_history,
        )
        return replace(final, llm_usage=summarize_llm_usage(inp.llm_usage_calls))

    if _is_off_topic_factory_question(inp.question):
        log.info("grounded_generate_off_topic_rejected", question=inp.question[:120])
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    if answer_path == "llm_unavailable":
        return GroundedGenerateResult(
            answer=UNAVAILABLE_ANSWER,
            cited_docs=[],
            answer_path="llm_unavailable",
            citations_verified=False,
            generation_mode="llm_unavailable",
            llm_usage=summarize_llm_usage(inp.llm_usage_calls),
        )

    log.info("grounded_generate_no_answer", question=inp.question[:120])
    return GroundedGenerateResult(
        answer=NO_DATA_ANSWER,
        cited_docs=[],
        answer_path="no_data",
        citations_verified=False,
        generation_mode="no_data",
        llm_usage=summarize_llm_usage(inp.llm_usage_calls),
    )
