"""Conversation-aware retrieval query rewriting (Phase 11)."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from spark.core.config import settings
from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger
from spark.retrieval.preprocess.follow_up import is_follow_up_question
from spark.services.session_slots import SessionSlots, requests_other_machine_scope

log = get_logger(__name__)

_REWRITE_PROFILE = "tagging"


def _session_machine_id(session_context: dict[str, Any]) -> str | None:
    confirmed = session_context.get("confirmed_machine_id")
    if confirmed:
        return str(confirmed).strip() or None
    machine = session_context.get("machine_id")
    return str(machine).strip() if machine else None


def _machine_missing(question: str, machine_id: str) -> bool:
    return machine_id.lower() not in (question or "").lower()


_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_LATIN_STOPWORDS = {"the", "and", "for", "with", "you", "are", "how", "what", "why"}


def _is_failed_answer(text: str) -> bool:
    """True when an assistant reply reported no answer (no-data/unavailable).

    A user turn that ended in no-data is a poor antecedent for a follow-up
    merge: gluing it into the retrieval query re-asks the question that just
    failed and displaces the turn the user is actually following up on.
    """
    head = (text or "").strip()[:160]
    if not head:
        return True
    from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER

    return (
        NO_DATA_ANSWER in head
        or UNAVAILABLE_ANSWER in head
        or "ไม่พบข้อมูล" in head
    )


def _topic_anchors(text: str) -> set[str]:
    from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens

    anchors = {token.upper() for token in extract_industrial_tokens(text)}
    anchors |= {
        word.lower()
        for word in _LATIN_WORD_RE.findall(text or "")
        if word.lower() not in _LATIN_STOPWORDS
    }
    return anchors


def _cut_at_word_boundary(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    cut = text[:budget]
    # Prefer breaking at whitespace when one exists in the back half — a
    # mid-word cut ("…ไฟจะ") feeds retrieval a token that matches nothing.
    space = cut.rfind(" ")
    if space >= budget // 2:
        cut = cut[:space]
    return cut.rstrip()


def _follow_up_antecedents(
    chat_history: list[tuple[str, str]],
    question: str,
) -> list[str]:
    """Prior user turns worth merging into a follow-up retrieval query.

    Pairs each topic-bearing user turn with the assistant reply that followed
    it and drops turns whose reply was no-data — then prefers turns sharing a
    topic anchor (device tag, alarm code, Latin term) with the current
    question, so "แล้วรีเซ็ต alarm นั้นล่ะ" binds to the alarm turn rather
    than whatever came last.
    """
    from spark.retrieval.preprocess.adaptive import classify_retrieval_need

    candidates: list[str] = []
    pending: str | None = None
    for role, content in chat_history:
        text = (content or "").strip()
        if role in ("human", "user"):
            if pending is not None:
                candidates.append(pending)
            pending = (
                text
                if text and classify_retrieval_need(text).decision == "retrieve"
                else None
            )
        else:
            if pending is not None and not _is_failed_answer(text):
                candidates.append(pending)
            pending = None
    if pending is not None:
        candidates.append(pending)

    question_anchors = _topic_anchors(question)
    if question_anchors:
        overlapped = [
            turn for turn in candidates if question_anchors & _topic_anchors(turn)
        ]
        if overlapped:
            return overlapped[-2:]
    return candidates[-2:]


def rules_rewrite_for_retrieval(
    question: str,
    chat_history: list[tuple[str, str]],
    session_context: dict[str, Any] | SessionSlots,
    *,
    has_prior_user_message: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Deterministic rewrite — merge session machine and prior user turn for follow-ups."""
    cleaned = (question or "").strip()
    meta: dict[str, Any] = {"strategy": "rules", "follow_up": False}

    if isinstance(session_context, SessionSlots):
        ctx = session_context.as_rewrite_context()
        locked_fields = set(session_context.locked_fields)
    else:
        ctx = session_context or {}
        locked_fields = set(ctx.get("locked_fields") or [])

    machine_id = _session_machine_id(ctx)
    follow_up = is_follow_up_question(
        cleaned,
        chat_history,
        has_prior_user_message=has_prior_user_message,
    )
    meta["follow_up"] = follow_up

    scope_clarify = bool(
        machine_id
        and "machine_id" in locked_fields
        and requests_other_machine_scope(cleaned, machine_id)
    )
    if scope_clarify:
        meta["scope_clarify"] = True
        meta["locked_machine_id"] = machine_id
        machine_id = None

    parts: list[str] = []
    if machine_id and _machine_missing(cleaned, machine_id):
        parts.append(machine_id)

    max_chars = settings.spark_query_rewrite_max_chars
    if follow_up:
        # Include up to two prior user turns (oldest first) — a follow-up may
        # reference the question before last ("แล้วอันที่ถามก่อนหน้านั้นล่ะ"),
        # which the single last-turn merge could never recover. Chitchat turns
        # ("สวัสดีครับ", "ขอบคุณครับ") carry no retrievable topic, turns whose
        # answer was no-data re-ask a question that just failed, and a turn
        # sharing a topic anchor with the current question beats plain
        # recency — all handled in _follow_up_antecedents.
        prior_users = _follow_up_antecedents(chat_history, cleaned)
        # The current question is reserved FIRST: it sits at the end of the
        # merged string, so letting priors spend the whole cap meant the final
        # truncation amputated the question itself (observed live: the merged
        # query ended mid-prior-turn and the actual question never reached
        # retrieval).
        reserved = sum(len(p) + 1 for p in parts) + len(cleaned)
        available = max_chars - reserved - len(prior_users)
        included: list[str] = []
        if prior_users and available >= 16:
            budget = available // len(prior_users)
            included = [
                cut
                for cut in (_cut_at_word_boundary(t, budget) for t in prior_users)
                if cut
            ]
        parts.extend(included)
        parts.append(cleaned)
        rewritten = " ".join(parts).strip()
        meta["prior_user_included"] = bool(included)
    elif parts:
        rewritten = f"{' '.join(parts)} {cleaned}".strip()
    else:
        rewritten = cleaned

    if len(rewritten) > max_chars:
        cut = rewritten[: max_chars - 1]
        space = cut.rfind(" ")
        if space >= (max_chars - 1) // 2:
            cut = cut[:space]
        rewritten = cut.rstrip() + "…"
        meta["truncated"] = True

    return rewritten, meta


async def _llm_rewrite_for_retrieval(
    question: str,
    chat_history: list[tuple[str, str]],
    session_context: dict[str, Any],
    *,
    llm: Any,
) -> str | None:
    history_lines: list[str] = []
    for role, content in chat_history[-6:]:
        label = "User" if role in ("human", "user") else "Assistant"
        history_lines.append(f"{label}: {(content or '')[:300]}")
    machine_id = _session_machine_id(session_context)
    machine_hint = f"\nLocked machine_id: {machine_id}" if machine_id else ""
    messages = [
        SystemMessage(
            content=(
                "Rewrite the latest user question into a standalone factory search query. "
                "Include machine codes and technical terms from chat history when implied. "
                "Thai or English is fine. Output ONLY the rewritten query, max 256 characters."
            )
        ),
        HumanMessage(
            content=(
                f"Chat history:\n{chr(10).join(history_lines) or '(none)'}"
                f"{machine_hint}\n\nLatest question: {question}"
            )
        ),
    ]
    response = await asyncio.wait_for(
        llm.ainvoke(messages),
        timeout=settings.spark_query_rewrite_timeout_sec,
    )
    raw = response.content if hasattr(response, "content") else str(response)
    rewritten = str(raw or "").strip()
    if not rewritten or len(rewritten) < 4:
        return None
    max_chars = settings.spark_query_rewrite_max_chars
    if len(rewritten) > max_chars:
        rewritten = rewritten[: max_chars - 1].rstrip() + "…"
    return rewritten


async def rewrite_for_retrieval(
    question: str,
    chat_history: list[tuple[str, str]],
    session_context: dict[str, Any] | SessionSlots,
    *,
    llm: Any | None = None,
    llm_rewrite_enabled: bool = True,
    has_prior_user_message: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Return ``(question_for_retrieval, metadata)``."""
    ctx = (
        session_context.as_rewrite_context()
        if isinstance(session_context, SessionSlots)
        else session_context
    )
    rules_question, meta = rules_rewrite_for_retrieval(
        question,
        chat_history,
        session_context,
        has_prior_user_message=has_prior_user_message,
    )

    if not llm_rewrite_enabled:
        meta["rewrite_verdict"] = "rules"
        return rules_question, meta

    if not meta.get("follow_up"):
        meta["rewrite_verdict"] = "standalone_rules"
        return rules_question, meta

    rewrite_llm = llm or get_chat_llm(_REWRITE_PROFILE)
    try:
        llm_question = await _llm_rewrite_for_retrieval(
            question,
            chat_history,
            ctx,
            llm=rewrite_llm,
        )
        if llm_question:
            if isinstance(session_context, SessionSlots):
                slots = session_context
            else:
                slots = SessionSlots.model_validate(
                    {
                        **ctx,
                        "locked_fields": ctx.get("locked_fields") or [],
                    }
                )
            from spark.retrieval.preprocess.rewrite_guard import validate_rewrite

            verdict = validate_rewrite(question, llm_question, slots)
            if not verdict.ok:
                meta["rewrite_rejected"] = verdict.reason
                meta["rewrite_verdict"] = verdict.reason or "rejected"
                meta["strategy"] = "rules_fallback"
                return rules_question, meta
            meta["strategy"] = "llm"
            meta["rewrite_verdict"] = "accepted"
            log.info(
                "query_rewrite_llm",
                question_raw=question[:120],
                question_retrieval=llm_question[:120],
                follow_up=meta.get("follow_up"),
            )
            return llm_question, meta
    except Exception as exc:
        log.warning("query_rewrite_llm_failed", error=str(exc)[:200])

    meta["strategy"] = "rules_fallback"
    meta.setdefault("rewrite_verdict", "rules_fallback")
    return rules_question, meta
