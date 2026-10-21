"""Thai output enforcement for generation (Phase 10)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from spark.retrieval.synthesis import _answer_too_english_for_thai_question, _thai_ratio

# Han ideographs / kana / hangul: the corpus is Thai/English, so CJK in an
# answer to a Thai question is always a broken generation (small multilingual
# models drift into Chinese), never legitimate quoted content.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")

_PROMPTS_PATH = Path(__file__).resolve().parents[3] / "configs" / "generation" / "prompts_v2.yaml"


@lru_cache(maxsize=1)
def thai_retry_addendum() -> str:
    if not _PROMPTS_PATH.is_file():
        return (
            "ตอบเป็นภาษาไทยเท่านั้น ทุกประโยคที่อ้างข้อเท็จจริงต้องลงท้ายด้วย [chunk_id:...]"
        )
    raw = yaml.safe_load(_PROMPTS_PATH.read_text(encoding="utf-8")) or {}
    return str(raw.get("thai_retry_addendum") or "").strip() or (
        "ตอบเป็นภาษาไทยเท่านั้น ทุกประโยคที่อ้างข้อเท็จจริงต้องลงท้ายด้วย [chunk_id:...]"
    )


def question_prefers_thai_output(question: str) -> bool:
    return _thai_ratio(question) >= 0.05


def answer_fails_thai_policy(question: str, answer: str) -> bool:
    if not question_prefers_thai_output(question):
        return False
    if _CJK_RE.search(answer or ""):
        return True
    return _answer_too_english_for_thai_question(question, answer)


def span_text_fails_thai_policy(question: str, span_text: str) -> bool:
    return question_prefers_thai_output(question) and _thai_ratio(span_text) < 0.12
