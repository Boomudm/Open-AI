"""Validated pseudo-streaming — emit tokens only after grounding checks (Phase 10)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, AsyncIterator, Literal

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import generation_stream_pseudo_total
from spark.generation.constrained_safety import intent_requires_structured_safety, run_constrained_safety
from spark.generation.context import append_readable_citations, build_grounded_context, llm_prompt_payload
from spark.generation.grounded_llm import _generation_retry_reason, run_grounded_llm
from spark.generation.pipeline import _apply_nli_gate, generate
from spark.generation.self_verify import self_verify_answer
from spark.generation.types import GenerationInput, GroundedGenerateResult
from spark.generation.usage import record_llm_usage, summarize_llm_usage
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent

log = get_logger(__name__)

StreamEventKind = Literal["token", "token_provisional", "citation_block", "done", "error"]


@dataclass(frozen=True)
class StreamEvent:
    kind: StreamEventKind
    delta: str = ""
    result: GroundedGenerateResult | None = None
    message: str = ""


def iter_stream_deltas(text: str, *, chunk_size: int = 16) -> list[str]:
    """Split finalized text into incremental SSE-sized chunks."""
    if not text:
        return []
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


# Thai combining vowel signs and tone marks — these always attach to the
# immediately preceding consonant and can never be legitimately separated
# from it by whitespace. Some LLM/proxy token streams insert a stray space
# when a streamed token boundary happens to fall between a consonant and its
# own combining mark (e.g. "ที่" arrives as "ท" + " ี" + "่"), which renders
# as visibly broken Thai ("ท ี ่").
_THAI_COMBINING_MARKS = "ัิีึืฺุู็่้๊๋์ํ๎"
_THAI_SPACE_BEFORE_COMBINING_RE = re.compile(rf"[ \t]+(?=[{_THAI_COMBINING_MARKS}])")


def _strip_thai_combining_spacing(text: str) -> str:
    return _THAI_SPACE_BEFORE_COMBINING_RE.sub("", text)


class _ThaiStreamSpacingFixer:
    """Repairs stray whitespace between a Thai consonant and its combining
    mark when that whitespace is introduced right at a streamed chunk
    boundary (so a single-chunk regex pass can't see it)."""

    def __init__(self) -> None:
        self._pending_space = False

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        prefix = ""
        if self._pending_space:
            self._pending_space = False
            if delta[0] not in _THAI_COMBINING_MARKS:
                prefix = " "
        delta = _strip_thai_combining_spacing(delta)
        if delta.endswith((" ", "\t")):
            self._pending_space = True
            delta = delta[:-1]
        return prefix + delta

    def flush(self) -> str:
        if self._pending_space:
            self._pending_space = False
            return " "
        return ""


def _chunk_text(chunk: Any) -> str:
    if hasattr(chunk, "content"):
        raw = chunk.content
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            return "".join(
                part.get("text", part) if isinstance(part, dict) else str(part)
                for part in raw
            )
    return str(chunk or "")


async def _yield_text_as_tokens(text: str) -> AsyncIterator[StreamEvent]:
    for delta in iter_stream_deltas(_strip_thai_combining_spacing(text)):
        yield StreamEvent(kind="token", delta=delta)


async def _stream_llm_tokens_live(inp: GenerationInput) -> AsyncIterator[StreamEvent]:
    """Live token stream — provisional deltas until citation validation succeeds."""
    import asyncio

    from spark.generation.citations import citation_validation_failure, validate_grounded_citations
    from spark.generation.grounded_llm import _retry_thai_grounded_llm
    from spark.generation.thai_enforce import answer_fails_thai_policy
    from spark.generation.prompts import rag_prompt

    active_prompt = getattr(inp, "prompt_template", None) or rag_prompt
    use_provisional = settings.app_profile.stream_tokens_provisional_only
    provisional_kind: StreamEventKind = "token_provisional" if use_provisional else "token"

    def _check_cancel() -> None:
        cancel = getattr(inp, "cancel_event", None)
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError("stream cancelled by client disconnect")

    from spark.generation.unverified import flag_or_suppress

    # Flag-vs-suppress uses safety INTENT (LOTO / lockout / hazard) plus the
    # genuinely safety-critical doc types — NOT machine_manual, which covers
    # ordinary factual lookups ("what temperature does this alarm trigger"). A
    # correct, cited answer to a non-safety machine question must not be
    # silently discarded just because its source is a manual.
    _STRICT_SAFETY_DOCS = {"sop", "safety_certificate", "safety_procedure"}
    _doc_types = [str(d.payload.get("document_type") or "") for d in inp.docs]
    _is_safety = (
        detect_safety_intent(inp.question).kind != SafetyIntentKind.NONE
        or bool(_STRICT_SAFETY_DOCS & set(_doc_types))
    )

    context = build_grounded_context(inp.docs)
    if not context.strip():
        yield StreamEvent(
            kind="done",
            result=GroundedGenerateResult(
                answer=NO_DATA_ANSWER,
                cited_docs=[],
                answer_path="no_data",
                citations_verified=False,
                generation_mode="no_data",
            ),
        )
        return

    prompt_question = inp.synthesis_question or inp.question
    payload = llm_prompt_payload(
        context=context,
        question=prompt_question,
        chat_history=inp.chat_history,
    )

    buffer = ""
    answer_path = "grounded_llm"
    spacing_fixer = _ThaiStreamSpacingFixer()
    live_streamed = False

    def _with_usage(final: GroundedGenerateResult) -> GroundedGenerateResult:
        return replace(final, llm_usage=summarize_llm_usage(inp.llm_usage_calls))

    async def _emit_final_answer(final: GroundedGenerateResult) -> AsyncIterator[StreamEvent]:
        """Emit the authoritative answer text, superseding anything streamed live.

        The client renders provisional deltas as they arrive and only swaps them
        out on a citation_block frame, so every terminal path that rejects the
        streamed text — verified rewrite, NLI gate, numeric fabrication, no-data
        suppression — has to come through here. Ending on a bare `done` leaves
        the rejected text on screen while the stored message says something else.
        """
        final = _with_usage(final)
        if live_streamed:
            yield StreamEvent(kind="citation_block", result=final)
            yield StreamEvent(kind="done", result=final)
            return
        async for tok in _yield_text_as_tokens(final.answer):
            yield tok
        yield StreamEvent(kind="citation_block", result=final)
        yield StreamEvent(kind="done", result=final)

    async def _emit_flagged_final(final: GroundedGenerateResult) -> AsyncIterator[StreamEvent]:
        """Flag-don't-suppress: show the answer plus the unverified note.

        When the body already streamed live, only the trailing note needs to be
        emitted; otherwise emit the full flagged answer (which already carries the
        note suffix)."""
        from spark.retrieval.constants import UNVERIFIED_ANSWER_SUFFIX

        final = _with_usage(final)
        if live_streamed:
            async for tok in _yield_text_as_tokens(UNVERIFIED_ANSWER_SUFFIX):
                yield tok
        else:
            async for tok in _yield_text_as_tokens(final.answer):
                yield tok
        yield StreamEvent(kind="citation_block", result=final)
        yield StreamEvent(kind="done", result=final)

    try:
        formatted = await active_prompt.ainvoke(payload)
        stream_fn = getattr(inp.llm, "astream", None)
        if callable(stream_fn):
            live_streamed = True
            async for chunk in stream_fn(formatted):
                _check_cancel()
                record_llm_usage(inp, chunk, llm=inp.llm, operation="grounded_llm_stream")
                raw_delta = _chunk_text(chunk)
                if not raw_delta:
                    continue
                delta = spacing_fixer.feed(raw_delta)
                if not delta:
                    continue
                buffer += delta
                yield StreamEvent(kind=provisional_kind, delta=delta)
            tail = spacing_fixer.flush()
            if tail:
                buffer += tail
                yield StreamEvent(kind=provisional_kind, delta=tail)
        else:
            response = await asyncio.wait_for(
                inp.llm.ainvoke(formatted),
                timeout=settings.rag_llm_timeout_sec,
            )
            record_llm_usage(inp, response, llm=inp.llm, operation="grounded_llm")
            buffer = _strip_thai_combining_spacing(_chunk_text(response).strip())
    except TimeoutError:
        log.error("rag_llm_timeout", timeout=settings.rag_llm_timeout_sec)
        yield StreamEvent(kind="error", message="rag_llm_timeout")
        answer_path = "llm_unavailable"
        buffer = ""
    except Exception as exc:
        log.error("rag_llm_stream_failed", error=str(exc)[:500])
        yield StreamEvent(kind="error", message="rag_llm_stream_failed")
        answer_path = "llm_unavailable"
        buffer = ""

    if buffer and answer_path == "grounded_llm" and settings.rag_generation_retry_enabled:
        retry_reason = _generation_retry_reason(buffer)
        if retry_reason:
            log.info("stream_regenerate", reason=retry_reason, first_preview=buffer[:80])
            try:
                response = await asyncio.wait_for(
                    inp.llm.ainvoke(formatted),
                    timeout=settings.rag_llm_timeout_sec,
                )
                record_llm_usage(inp, response, llm=inp.llm, operation="grounded_llm_retry")
                second = _strip_thai_combining_spacing(_chunk_text(response).strip())
                second_valid, _ = validate_grounded_citations(
                    second, inp.docs, question=inp.question
                )
                # The provisional refusal already reached the client, and the
                # frontend's authoritative replacement is the citation_block /
                # done text of the *verified* finalisation path — so only adopt
                # a retry that fully validates; anything weaker keeps the
                # original buffer and the existing finalisation semantics.
                if second and second_valid and _generation_retry_reason(second) is None:
                    buffer = second
            except Exception as exc:
                log.warning("stream_regenerate_failed", error=str(exc)[:200])

    if buffer:
        valid, cited_docs = validate_grounded_citations(buffer, inp.docs, question=inp.question)
        if valid:
            if answer_fails_thai_policy(inp.question, buffer):
                retry = await _retry_thai_grounded_llm(
                    llm=inp.llm,
                    question=prompt_question,
                    context=context,
                    chat_history=inp.chat_history,
                )
                if retry:
                    valid_retry, cited_retry = validate_grounded_citations(retry, inp.docs, question=inp.question)
                    if valid_retry and not answer_fails_thai_policy(inp.question, retry):
                        final = GroundedGenerateResult(
                            answer=append_readable_citations(retry, cited_retry),
                            cited_docs=cited_retry,
                            answer_path="grounded_llm",
                            citations_verified=True,
                            generation_mode="grounded_llm",
                        )
                        final = await _apply_nli_gate(inp.question, final, context=context)
                        if final.answer_path == "nli_gate_fail":
                            async for event in _emit_final_answer(final):
                                yield event
                            return
                        sv = await self_verify_answer(inp.question, final, inp.docs)
                        if sv.needs_correction:
                            log.info("stream_self_verify_fail", score=sv.verification_score, safety=_is_safety)
                            final = await flag_or_suppress(
                                final.answer, inp.docs,
                                is_safety=_is_safety, reason="self_verify_fail",
                                llm=inp.llm, question=inp.question, chat_history=inp.chat_history,
                            )
                            emit = _emit_flagged_final if final.answer_path == "grounded_unverified" else _emit_final_answer
                            async for event in emit(final):
                                yield event
                            return
                        async for event in _emit_final_answer(final):
                            yield event
                        return
            else:
                final = GroundedGenerateResult(
                    answer=append_readable_citations(buffer, cited_docs),
                    cited_docs=cited_docs,
                    answer_path=answer_path,
                    citations_verified=True,
                    generation_mode="grounded_llm",
                )
                final = await _apply_nli_gate(inp.question, final, context=context)
                if final.answer_path == "nli_gate_fail":
                    async for event in _emit_final_answer(final):
                        yield event
                    return
                sv = await self_verify_answer(inp.question, final, inp.docs)
                if sv.needs_correction:
                    log.info("stream_self_verify_fail", score=sv.verification_score, safety=_is_safety)
                    final = await flag_or_suppress(
                        final.answer, inp.docs,
                        is_safety=_is_safety, reason="self_verify_fail",
                        llm=inp.llm, question=inp.question, chat_history=inp.chat_history,
                    )
                    emit = _emit_flagged_final if final.answer_path == "grounded_unverified" else _emit_final_answer
                    async for event in emit(final):
                        yield event
                    return
                async for event in _emit_final_answer(final):
                    yield event
                return

        failure_reason = citation_validation_failure(buffer, inp.docs, question=inp.question)
        if use_provisional:
            log.info(
                "stream_citation_validation_fallback",
                reason=failure_reason or "citation_validation_failed",
            )
        if failure_reason == "numeric_grounding_fail":
            # A number contradicting the cited evidence is a fabrication — never
            # show it, not even flagged.
            log.info("stream_numeric_fail_suppressed", question=inp.question[:120])
            async for event in _emit_final_answer(
                GroundedGenerateResult(
                    answer=NO_DATA_ANSWER,
                    cited_docs=[],
                    answer_path="numeric_grounding_fail",
                    citations_verified=False,
                    generation_mode="no_data",
                )
            ):
                yield event
            return

    if buffer:
        # Real content that missed full validation: flag-and-show whenever
        # retrieval found source documents instead of silently returning no-data.
        final = await flag_or_suppress(
            buffer, inp.docs, is_safety=_is_safety, reason="citation_incomplete",
            llm=inp.llm, question=inp.question, chat_history=inp.chat_history,
        )
        if final.answer_path == "grounded_unverified":
            async for event in _emit_flagged_final(final):
                yield event
        else:
            async for event in _emit_final_answer(final):
                yield event
        return

    async for event in _emit_final_answer(await run_grounded_llm(inp)):
        yield event


async def _stream_validated_pseudo(inp: GenerationInput) -> AsyncIterator[StreamEvent]:
    """Run full generation + validation, then emit chunk deltas from the final answer."""
    from spark.core.config import settings as app_settings

    if app_settings.app_env.strip().lower() == "production":
        log.warning("generation_pseudo_stream_in_production")
    generation_stream_pseudo_total.inc()
    output = await generate(inp)
    result = replace(output.result, llm_usage=summarize_llm_usage(inp.llm_usage_calls))
    if result.answer:
        async for event in _yield_text_as_tokens(result.answer):
            yield event
    yield StreamEvent(kind="done", result=result)


async def stream_grounded_answer(inp: GenerationInput) -> AsyncIterator[StreamEvent]:
    """Stream generation events — live tokens by default; pseudo-stream in test profile only."""
    if not inp.docs:
        yield StreamEvent(
            kind="done",
            result=GroundedGenerateResult(
                answer=NO_DATA_ANSWER,
                cited_docs=[],
                answer_path="no_data",
                citations_verified=False,
                generation_mode="no_data",
                llm_usage=summarize_llm_usage(inp.llm_usage_calls),
            ),
        )
        return

    if settings.effective_spark_stream_live_tokens:
        always_live = bool(getattr(settings, "spark_stream_always_live", False))
        safety = detect_safety_intent(inp.question)
        _has_numeric = bool(re.search(r"\d+(?:\.\d+)?\s*(?:°C|bar|psi|rpm|mm|kg|kW|MPa|Nm)", inp.question))
        if not always_live and (safety.kind != SafetyIntentKind.NONE or _has_numeric):
            log.info("stream_safety_pseudo", intent=safety.kind.value, has_numeric=_has_numeric)
            async for event in _stream_validated_pseudo(inp):
                yield event
            return

        if not always_live and intent_requires_structured_safety(inp.question):
            structured = await run_constrained_safety(inp)
            if structured.citations_verified:
                async for event in _yield_text_as_tokens(structured.answer):
                    yield event
                yield StreamEvent(kind="done", result=structured)
                return

        async for event in _stream_llm_tokens_live(inp):
            yield event
        return

    async for event in _stream_validated_pseudo(inp):
        yield event


async def stream_generation(inp: GenerationInput) -> AsyncIterator[StreamEvent]:
    """Alias for stream_grounded_answer — used by RAGService stream path."""
    async for event in stream_grounded_answer(inp):
        yield event
