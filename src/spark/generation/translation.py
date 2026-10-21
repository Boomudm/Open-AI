"""Operator-facing translation — dedicated profile, not regex glossary (Phase 9)."""

from __future__ import annotations

import asyncio
import re

from langchain_core.messages import HumanMessage, SystemMessage

from spark.core.config import settings
from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger
from spark.retrieval.synthesis import _thai_ratio

log = get_logger(__name__)

_TRANSLATE_PROFILE = "translate_th"

# Han ideographs / kana / hangul. Small multilingual models asked for Thai
# sometimes emit Chinese instead ("เปลี่ยน机油 使用黄油枪..."); that is a failed
# translation, and the English original is strictly better for the operator.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


async def translate_for_operator(text: str, target_lang: str = "th") -> str:
    """Translate maintenance text for Thai operators using the translate_th profile."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    if target_lang.lower().startswith("th") and _thai_ratio(cleaned) >= 0.25:
        return cleaned

    llm = get_chat_llm(_TRANSLATE_PROFILE)
    messages = [
        SystemMessage(
            content=(
                "You translate factory maintenance text into clear, natural Thai "
                "for machine operators. Preserve every number, unit, part code, "
                "model name, and signal/tag identifier (e.g. RES0.xxx, CN7, AWG24) "
                "exactly as written — never translate or respell identifiers. "
                "Preserve safety warnings exactly. Do not add or remove steps. "
                "Output only the translation, no commentary."
            )
        ),
        HumanMessage(content=cleaned),
    ]
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=settings.rag_llm_timeout_sec,
        )
        translated = str(getattr(response, "content", response) or "").strip()
        if _CJK_RE.search(translated):
            log.warning("translate_for_operator_cjk_output", preview=translated[:120])
            return cleaned
        return translated or cleaned
    except Exception as exc:
        log.warning("translate_for_operator_failed", error=str(exc)[:200])
        return cleaned
