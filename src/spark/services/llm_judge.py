"""Central single-token LLM judge for language-interpretation decisions.

Use this for decisions that are about UNDERSTANDING LANGUAGE (intent, topic
continuity, chitchat vs work question). Never use it for facts, tenancy,
ACL, citation validation, or injection scanning — those must stay
deterministic (see 2026-07 product notes).

Contract: ask the chat model to answer with exactly one word from `choices`.
Any failure — timeout, transport error, out-of-vocabulary reply — returns
None and the caller falls back to its deterministic heuristic. Judges must
always be an accuracy upgrade, never a new failure mode.
"""

from __future__ import annotations

import asyncio

from spark.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_TIMEOUT_SEC = 8.0


async def judge_one_word(
    prompt: str,
    choices: list[str],
    *,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> str | None:
    """Return one of ``choices`` (uppercased comparison) or None on any failure."""
    from spark.core.config import settings

    # Unit tests must stay hermetic — a live local Ollama would otherwise be
    # called for real and burn the request deadline.
    if settings.spark_profile == "test" or settings.spark_testing:
        return None
    try:
        from spark.core.llm_client import get_chat_llm

        llm = get_chat_llm()
        full_prompt = f"{prompt}\nตอบคำเดียวเท่านั้นจากตัวเลือก: {', '.join(choices)}"
        response = await asyncio.wait_for(llm.ainvoke(full_prompt), timeout=timeout_sec)
        verdict = str(getattr(response, "content", response) or "").strip().upper()
        for choice in choices:
            if verdict.startswith(choice.upper()):
                return choice
        log.info("llm_judge_out_of_vocab", verdict=verdict[:40])
        return None
    except Exception as exc:  # noqa: BLE001 — judge is best-effort by contract
        log.info("llm_judge_unavailable", error=str(exc)[:120])
        return None
