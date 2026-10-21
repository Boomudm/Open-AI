from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Intent = Literal["factual", "followup", "unknown"]
Route = Literal["rag"]

# Anchored follow-up cues. Bare "แล้ว"/"นั้น" used to match as substrings —
# both are everyday Thai words ("ตรวจสอบแล้วพบว่า...", "ค่านั้นๆ") so brand-new
# questions were dragged into the previous topic, while real follow-ups
# phrased without them ("ขอรายละเอียดเพิ่ม", "หน้าไหน") were missed.
FOLLOWUP_KEYWORDS = [
    "ของมัน",
    "ตัวเดียวกัน",
    "อันนั้น",
    "ตัวนั้น",
    "เครื่องนั้น",
    "ข้อนั้น",
    "เรื่องนั้น",
    "รุ่นนั้น",
    "ดังกล่าว",
    "ตามที่ถาม",
    "เพิ่มเติม",
    "อีกที",
    "ขยายความ",
    "ก่อนหน้า",
    "เมื่อกี้",
    "เมื่อสักครู่",
    "ที่ตอบมา",
    "คำตอบเดิม",
]

# Patterns that only signal a follow-up in a specific position: leading
# "แล้ว..." ("แล้วรุ่นใหญ่ล่ะ") or trailing "...ล่ะ/หรอ/เหรอ".
_FOLLOWUP_ANCHORED_RE = re.compile(r"^\s*แล้ว|(?:ล่ะ|หรอ|เหรอ)\s*[?]?\s*$")

DOCUMENT_HINT_KEYWORDS = [
    "เอกสาร",
    "คู่มือ",
    "manual",
    "uploaded",
    "according to",
    "จากเอกสาร",
    "source file",
    "ในเอกสาร",
    "in the document",
    "the document",
    "document proof",
]


@dataclass(frozen=True)
class QuestionRouting:
    """RAG-only routing with optional follow-up contextualization."""

    route: Route
    is_followup: bool
    reason: str
    confidence: float = 1.0


def _has_document_context(question_lower: str, document_type: str | None) -> bool:
    if document_type and str(document_type).strip():
        return True
    return any(k in question_lower for k in DOCUMENT_HINT_KEYWORDS)


def _has_followup_signal(question_lower: str) -> bool:
    if len(question_lower) >= 80:
        return False
    if any(k in question_lower for k in FOLLOWUP_KEYWORDS):
        return True
    return bool(_FOLLOWUP_ANCHORED_RE.search(question_lower))


def routing_to_intent(routing: QuestionRouting) -> Intent:
    if routing.reason == "too_short":
        return "unknown"
    if routing.is_followup:
        return "followup"
    return "factual"


def route_question(
    question: str,
    *,
    document_type: str | None = None,
    has_prior_user_message: bool = False,
) -> QuestionRouting:
    """Heuristic router — always RAG; detects follow-up turns."""
    q = question.lower()
    if not re.search(r"[\w\u0E00-\u0E7F]{3,}", q):
        return QuestionRouting(route="rag", is_followup=False, reason="too_short", confidence=0.0)

    followup_signal = _has_followup_signal(q)
    document_ctx = _has_document_context(q, document_type)

    if document_ctx:
        is_followup = followup_signal and has_prior_user_message
        return QuestionRouting(
            route="rag",
            is_followup=is_followup,
            reason="document_filter",
            confidence=0.95,
        )

    if followup_signal and has_prior_user_message:
        return QuestionRouting(route="rag", is_followup=True, reason="keyword:followup", confidence=0.9)

    return QuestionRouting(route="rag", is_followup=False, reason="default:factual", confidence=0.5)


# LLM judge for topic continuity. Follow-up-ness is a RELATION to the prior
# conversation — keyword lists can't see it, and bge-m3 cosine on short Thai
# question pairs measured too poorly to separate (related ~0.35 vs unrelated
# up to ~0.45). A 1-token YES/NO from the chat model is ~1-2s on the gateway
# and understands Thai subject omission. Fails safe: any error/timeout means
# "not a follow-up", because dragging stale context into a new topic gave
# users wrong answers (observed with the EE-07 question), while a missed
# follow-up just retrieves standalone — and the anaphora layer still catches
# questions that cannot stand alone at all.
_FOLLOWUP_JUDGE_TIMEOUT_SEC = 8.0


async def _semantic_followup(question: str, prior_question: str) -> bool | None:
    from spark.services.llm_judge import judge_one_word

    verdict = await judge_one_word(
        (
            "ตัดสินว่า 'คำถามใหม่' เป็นคำถามต่อเนื่องที่ต้องอาศัยบริบทจาก 'คำถามก่อนหน้า' "
            "จึงจะเข้าใจครบถ้วนหรือไม่ ถ้าเป็นคนละเรื่อง/ยืนเดี่ยวได้ให้ตอบ NO\n"
            f"คำถามก่อนหน้า: {prior_question[:300]}\n"
            f"คำถามใหม่: {question[:300]}"
        ),
        ["YES", "NO"],
    )
    if verdict is None:
        return None
    return verdict == "YES"


async def resolve_routing(
    question: str,
    *,
    document_type: str | None = None,
    has_prior_user_message: bool = False,
    prior_question: str | None = None,
) -> QuestionRouting:
    """RAG routing with two-stage follow-up detection.

    1. Anaphora/deixis patterns (high precision — "อันนั้น", trailing "ล่ะ"):
       the question cannot stand alone, keyword verdict is trusted.
    2. Otherwise, semantic similarity against the previous user question
       decides topic continuity — no word lists involved.
    """
    keyword_routing = route_question(
        question,
        document_type=document_type,
        has_prior_user_message=has_prior_user_message,
    )
    if keyword_routing.is_followup:
        return keyword_routing
    if has_prior_user_message and (prior_question or "").strip():
        semantic = await _semantic_followup(question, str(prior_question))
        if semantic is True:
            return QuestionRouting(
                route="rag",
                is_followup=True,
                reason="semantic:followup",
                confidence=0.75,
            )
    return keyword_routing


async def _legacy_resolve_routing(
    question: str,
    *,
    document_type: str | None = None,
    has_prior_user_message: bool = False,
) -> QuestionRouting:
    return route_question(
        question,
        document_type=document_type,
        has_prior_user_message=has_prior_user_message,
    )


async def classify_intent(
    question: str,
    *,
    document_type: str | None = None,
    has_prior_user_message: bool = False,
) -> Intent:
    """Backward-compatible intent label derived from QuestionRouting."""
    routing = await resolve_routing(
        question,
        document_type=document_type,
        has_prior_user_message=has_prior_user_message,
    )
    return routing_to_intent(routing)
