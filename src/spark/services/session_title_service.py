from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_TITLES = frozenset({"new chat", "new_chat", "แชทใหม่"})
HEURISTIC_MAX = 40
LLM_TRIGGER_LEN = 80
TITLE_MAX = 200


def is_default_title(title: str | None) -> bool:
    if not title or not title.strip():
        return True
    return title.strip().lower() in DEFAULT_TITLES


def needs_llm_title(question: str, heuristic_title: str) -> bool:
    q = question.strip()
    if len(q) > LLM_TRIGGER_LEN:
        return True
    if q.count("?") + q.count("？") > 1 or q.count(".") + q.count("。") > 2:
        return True
    if len(heuristic_title) >= HEURISTIC_MAX - 3:
        return True
    return False


def _heuristic_title(question: str, *, machine_id: str | None) -> str:
    text = re.sub(r"\s+", " ", question.strip())
    if not text:
        return "แชทใหม่"
    title = text[:HEURISTIC_MAX].rstrip()
    if len(text) > HEURISTIC_MAX:
        title = title.rstrip(".,;:!?。，、") + "…"
    if machine_id:
        prefix = f"{machine_id} · "
        if len(prefix) + len(title) <= TITLE_MAX:
            title = prefix + title
    return title[:TITLE_MAX]


async def _llm_title(question: str, *, machine_id: str | None) -> str | None:
    try:
        llm = get_chat_llm("tagging")
        machine_hint = f"Machine: {machine_id}. " if machine_id else ""
        resp = await llm.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Summarize the user question as a short chat title (max 6 words). "
                        "Use the same language as the question (Thai or English). "
                        "No quotes, no punctuation at the end. Title only."
                    )
                ),
                HumanMessage(content=f"{machine_hint}Question: {question[:500]}"),
            ]
        )
        raw = (resp.content or "").strip().strip('"\'')
        if not raw:
            return None
        return raw[:TITLE_MAX]
    except Exception as exc:
        log.warning("session_title_llm_failed", error=str(exc)[:200])
        return None


async def generate_session_title(question: str, *, machine_id: str | None = None) -> str:
    heuristic = _heuristic_title(question, machine_id=machine_id)
    if needs_llm_title(question, heuristic):
        llm_result = await _llm_title(question, machine_id=machine_id)
        if llm_result:
            return llm_result
    return heuristic
