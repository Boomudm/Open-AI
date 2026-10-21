"""Follow-up question detection for conversational retrieval (Phase 11)."""

from __future__ import annotations

import re

# Thai + EN markers for dependent follow-up turns (not standalone new topics).
FOLLOW_UP_MARKERS = (
    "ทำต่อ",
    "ขั้นตอนถัดไป",
    "step 2",
    "step two",
    "next step",
    "continue",
    "then what",
    "what about",
    "and then",
    "แล้ว",
    "ของมัน",
    "ตัวเดียวกัน",
    "อันนั้น",
    "นั้น",
    "ดังกล่าว",
    "ตามที่ถาม",
    "อีก",
    "เพิ่มเติม",
    "รายละเอียด",
    "ชี้แจง",
    "explain more",
    "more detail",
)

NEW_TOPIC_MARKERS = (
    "machine ",
    "mc-",
    "servo",
    "motor",
    "เครื่อง",
    "มอเตอร์",
    "เซervo",
    "mc ",
)

_MC_ID_RE = re.compile(r"\bMC-\d{3,5}\b", re.IGNORECASE)
_TECH_ID_RE = re.compile(
    r"(?i)\b(?:[A-Z]{1,12}[_/-]?[A-Z0-9]*\d[A-Z0-9_/-]*|KR\s*C\d+|CC\d+[A-Z0-9-]*)\b"
)
_STANDALONE_QUESTION_MIN_LEN = 48
_CONTINUATION_PREFIXES = (
    "แล้ว",
    "ต่อ",
    "ถัดไป",
    "อีก",
    "what about",
    "and ",
    "then ",
)
_DEICTIC_MARKERS = (
    "ของมัน",
    "ตัวเดียวกัน",
    "อันนั้น",
    "อันนี้",
    "ตัวนั้น",
    "ตัวนี้",
    "เครื่องนั้น",
    "เครื่องนี้",
    "ดังกล่าว",
    "ตามที่ถาม",
    # n-2 back-references — the user points at an EARLIER turn, not the last one.
    "ก่อนหน้านั้น",
    "ก่อนหน้านี้",
    "คำถามแรก",
    "ข้อแรก",
    "เมื่อกี้",
    "เมื่อสักครู่",
    "the one before",
    "previous question",
    "first question",
    "earlier question",
)
_STANDALONE_QUESTION_MARKERS = (
    "อะไร",
    "อะไรบ้าง",
    "ไหน",
    "หน้าไหน",
    "กี่",
    "เท่าไร",
    "เท่าไหร่",
    "ตัวไหน",
    "รุ่นอะไร",
)
_STANDALONE_TOPIC_MARKERS = (
    "มอเตอร์",
    "motor",
    "ไดรฟ์",
    "drive",
    "สัญญาณ",
    "signal",
    "สาย",
    "cable",
    "interface board",
    "wiring diagram",
    "แบบไฟฟ้า",
    "modbus",
    "symbolic",
    "พารามิเตอร์",
    "parameter",
    "อะไหล่",
    "ราคา",
)


def machine_ids_in_text(text: str) -> list[str]:
    return [match.group(0).upper() for match in _MC_ID_RE.finditer(text or "")]


def _last_user_turn(chat_history: list[tuple[str, str]]) -> str | None:
    for role, content in reversed(chat_history):
        if role in ("human", "user"):
            text = (content or "").strip()
            if text:
                return text
    return None


def _starts_with_continuation_marker(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(marker) for marker in _CONTINUATION_PREFIXES)


def _has_deictic_marker(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _DEICTIC_MARKERS)


def _has_standalone_signal(text: str) -> bool:
    lower = text.lower()
    if _MC_ID_RE.search(text) or _TECH_ID_RE.search(text):
        return True
    has_topic = any(marker in lower for marker in _STANDALONE_TOPIC_MARKERS)
    has_question = any(marker in lower for marker in _STANDALONE_QUESTION_MARKERS)
    return has_topic and has_question


def is_follow_up_question(
    question: str,
    chat_history: list[tuple[str, str]] | None,
    *,
    has_prior_user_message: bool = False,
) -> bool:
    """True when the question likely depends on prior chat context."""
    cleaned = (question or "").strip()
    if not cleaned:
        return False

    history = chat_history or []
    if not has_prior_user_message and not _last_user_turn(history):
        return False

    lower = cleaned.lower()
    if _starts_with_continuation_marker(cleaned) or _has_deictic_marker(cleaned):
        return True

    if _has_standalone_signal(cleaned):
        return False
    if len(cleaned) >= _STANDALONE_QUESTION_MIN_LEN:
        return False
    if any(marker in lower for marker in NEW_TOPIC_MARKERS):
        return False

    if any(marker in lower for marker in FOLLOW_UP_MARKERS):
        return len(cleaned) < 120

    return False
