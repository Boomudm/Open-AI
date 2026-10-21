"""Adaptive retrieval — decide whether to retrieve at all before hitting the pipeline.

Skips retrieval for greetings, chitchat, meta questions ("คุณชื่ออะไร"),
and simple acknowledgments ("ขอบคุณ", "เข้าใจแล้ว") that don't need documents.

Returns a direct answer instead of routing through the full RAG pipeline,
saving ~2-5s latency and unnecessary compute.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

RetrievalDecision = Literal["retrieve", "skip_chitchat", "skip_meta"]

_GREETING_PATTERNS = [
    re.compile(r"^(สวัสดี|หวัดดี|ดีครับ|ดีค่ะ|ดีจ้า|hello|hi|hey|good\s*morning|good\s*afternoon|good\s*evening)\s*(ครับ|ค่ะ|คับ|นะ|จ้า)?\s*[.!?ๆ]*$", re.IGNORECASE),
]

_SMALLTALK_PATTERNS = [
    re.compile(r"^(วันนี้\s*)?(เป็นไง|เป็นยังไง|สบายดีไหม|สบายดีมั้ย|how are you|how's it going)\s*(ครับ|ค่ะ|คับ|นะ|จ้า)?\s*[.!?ๆ]*$", re.IGNORECASE),
    re.compile(r"^(คุยเล่น|คุยเรื่อยเปื่อย|คุยกันเล่นๆ)\s*(ได้ไหม|ได้มั้ย|หน่อย)?\s*(ครับ|ค่ะ|คับ|นะ|จ้า)?\s*[.!?ๆ]*$", re.IGNORECASE),
]

_THANKS_PATTERNS = [
    re.compile(r"^(ขอบคุณ|ขอบใจ|thank|thanks|thx|ty)\s*[ครับค่ะนะจ้ามากๆ you so much very]*[.!?]*$", re.IGNORECASE),
]

_ACKNOWLEDGE_PATTERNS = [
    re.compile(r"^(เข้าใจแล้ว|โอเค|ok|okay|ได้เลย|รับทราบ|noted|got it|understood)\s*[ครับค่ะนะ]*[.!?]*$", re.IGNORECASE),
]

_META_PATTERNS = [
    re.compile(r"(คุณชื่ออะไร|คุณเป็นใคร|คุณทำอะไรได้|what.?s your name|who are you|what can you do)", re.IGNORECASE),
    re.compile(r"^(ช่วยอะไรได้บ้าง|help|ช่วยด้วย)\s*[ครับค่ะ?]*$", re.IGNORECASE),
]

_CHITCHAT_DIRECT_ANSWERS = {
    "skip_chitchat": {
        "greeting": "สวัสดีครับ ผม Neo ผู้ช่วย AI ประจำโรงงาน พร้อมช่วยเหลือเรื่องเครื่องจักร การซ่อมบำรุง และข้อมูลโรงงานครับ มีอะไรให้ช่วยไหมครับ?",
        "thanks": "ยินดีครับ หากมีคำถามเพิ่มเติมเรื่องเครื่องจักรหรือการซ่อมบำรุง สามารถถามได้เลยครับ",
        "acknowledge": "รับทราบครับ หากต้องการข้อมูลเพิ่มเติม สอบถามได้ตลอดครับ",
    },
    "skip_meta": {
        "identity": "ผมชื่อ Neo เป็น AI ผู้ช่วยประจำโรงงาน ช่วยค้นหาข้อมูลจากคู่มือเครื่องจักร ประวัติการซ่อม SOP และเอกสารโรงงานได้ครับ",
        "help": "ผม Neo ช่วยได้หลายเรื่องครับ เช่น:\n• ค้นหาข้อมูลจากคู่มือเครื่องจักร\n• ดูประวัติการซ่อมบำรุง\n• ตอบคำถามเรื่อง SOP และขั้นตอนความปลอดภัย\n• วิเคราะห์ข้อมูลซ่อมและอะไหล่\n\nลองถามได้เลยครับ!",
    },
}


@dataclass(frozen=True)
class AdaptiveResult:
    decision: RetrievalDecision
    direct_answer: str | None = None
    answer_category: str | None = None


_ALL_DIRECT_ANSWERS = frozenset(
    text for group in _CHITCHAT_DIRECT_ANSWERS.values() for text in group.values()
)

# The orchestrator's judge-fallback chitchat reply (chat_orchestrator).
# Matched by prefix so this module needn't import the orchestrator.
_FALLBACK_CHITCHAT_PREFIX = "คุยได้ครับ ผม Neo"


def is_direct_chitchat_answer(text: str) -> bool:
    """True when *text* is one of the canned no-retrieval chitchat replies.

    Used to recognize prior chitchat turns in the conversation history — a
    follow-up rewrite that merges prior questions must not glue a "พรุ่งนี้
    ฝนตกไหม" turn into a machinery search query.
    """
    t = (text or "").strip()
    if not t:
        return False
    return t in _ALL_DIRECT_ANSWERS or t.startswith(_FALLBACK_CHITCHAT_PREFIX)


def classify_retrieval_need(question: str) -> AdaptiveResult:
    """Classify whether a question needs retrieval or can be answered directly."""
    q = (question or "").strip()

    if not q or len(q) < 2:
        return AdaptiveResult(
            decision="skip_chitchat",
            direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_chitchat"]["greeting"],
            answer_category="empty",
        )

    for pattern in _GREETING_PATTERNS:
        if pattern.match(q):
            return AdaptiveResult(
                decision="skip_chitchat",
                direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_chitchat"]["greeting"],
                answer_category="greeting",
            )

    for pattern in _SMALLTALK_PATTERNS:
        if pattern.match(q):
            return AdaptiveResult(
                decision="skip_chitchat",
                direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_chitchat"]["greeting"],
                answer_category="smalltalk",
            )

    for pattern in _THANKS_PATTERNS:
        if pattern.match(q):
            return AdaptiveResult(
                decision="skip_chitchat",
                direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_chitchat"]["thanks"],
                answer_category="thanks",
            )

    for pattern in _ACKNOWLEDGE_PATTERNS:
        if pattern.match(q):
            return AdaptiveResult(
                decision="skip_chitchat",
                direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_chitchat"]["acknowledge"],
                answer_category="acknowledge",
            )

    for pattern in _META_PATTERNS:
        if pattern.search(q):
            category = "identity" if "ชื่อ" in q or "name" in q.lower() or "ใคร" in q else "help"
            return AdaptiveResult(
                decision="skip_meta",
                direct_answer=_CHITCHAT_DIRECT_ANSWERS["skip_meta"][category],
                answer_category=category,
            )

    return AdaptiveResult(decision="retrieve")
