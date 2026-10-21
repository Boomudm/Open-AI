"""Multi-hop query decomposition — split complex questions into atomic sub-queries.

Handles comparisons ("MC-001 พังบ่อยกว่า MC-002 ไหม"), multi-entity queries
("วิธีซ่อม pump และ valve ใน cooling system"), and conditional questions
("ถ้า pressure สูงกว่า 10 bar ต้องทำอย่างไร แล้วถ้าต่ำกว่าล่ะ").

Each sub-query is retrieved independently, then results are merged via RRF
before generation receives the combined evidence.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from spark.core.logging import get_logger

log = get_logger(__name__)

_DECOMPOSE_PROFILE = "tagging"

_COMPARISON_PATTERNS = [
    re.compile(r"(.+?)\s+(?:กับ|vs\.?|เทียบ(?:กับ)?|compared?\s+(?:to|with))\s+(.+)", re.IGNORECASE),
    re.compile(r"(.+?)\s+(?:ดีกว่า|แย่กว่า|บ่อยกว่า|มากกว่า|น้อยกว่า|better|worse|more|less)\s+(.+)", re.IGNORECASE),
]

_MULTI_ENTITY_PATTERN = re.compile(
    r"(.+?)\s+(?:และ|กับ|แล้วก็|and|plus|&)\s+(.+)",
    re.IGNORECASE,
)

_CONDITIONAL_PATTERN = re.compile(
    r"(.+?)\s+(?:แล้วถ้า|แต่ถ้า|ส่วนถ้า|and if|but if|what if)\s+(.+)",
    re.IGNORECASE,
)


@dataclass
class DecomposedQuery:
    original: str
    sub_queries: list[str]
    strategy: str
    needs_merge: bool = True


def _has_machine_ids(text: str) -> list[str]:
    return re.findall(r"[A-Z]{1,4}-\d{2,4}", text)


def _rules_decompose(question: str) -> DecomposedQuery | None:
    """Fast regex-based decomposition for common patterns."""
    q = question.strip()

    for pattern in _COMPARISON_PATTERNS:
        m = pattern.search(q)
        if m:
            machines = _has_machine_ids(q)
            if len(machines) >= 2:
                return DecomposedQuery(
                    original=q,
                    sub_queries=[
                        f"{machines[0]} {q}" if machines[0] not in m.group(1) else m.group(1).strip(),
                        f"{machines[1]} {q}" if machines[1] not in m.group(2) else m.group(2).strip(),
                    ],
                    strategy="comparison",
                )

    m = _CONDITIONAL_PATTERN.search(q)
    if m:
        return DecomposedQuery(
            original=q,
            sub_queries=[m.group(1).strip(), m.group(2).strip()],
            strategy="conditional",
        )

    return None


async def _llm_decompose(question: str) -> DecomposedQuery | None:
    """LLM-based decomposition for complex multi-hop questions."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from spark.core.llm_client import get_chat_llm

    prompt = (
        "คุณเป็น query decomposer สำหรับระบบค้นหาเอกสารโรงงาน\n"
        "ถ้าคำถามเป็นคำถามง่ายๆ ตอบ: SINGLE\n"
        "ถ้าคำถามซับซ้อน (เปรียบเทียบ, หลายหัวข้อ, หลายเงื่อนไข) "
        "ให้แยกเป็น sub-queries แต่ละบรรทัด:\n"
        "SUB: <sub-query 1>\n"
        "SUB: <sub-query 2>\n"
        "กฎ: แต่ละ sub-query ต้อง self-contained (มีบริบทเพียงพอ)"
    )

    try:
        llm = get_chat_llm(_DECOMPOSE_PROFILE)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=question[:1000]),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=6.0)
        text = str(getattr(response, "content", response) or "").strip()

        if "SINGLE" in text.upper():
            return None

        subs = [
            line.replace("SUB:", "").strip()
            for line in text.split("\n")
            if line.strip().startswith("SUB:")
        ]
        if len(subs) >= 2:
            return DecomposedQuery(
                original=question,
                sub_queries=subs[:4],
                strategy="llm",
            )
        return None
    except Exception as exc:
        log.warning("query_decompose_llm_failed", error=str(exc)[:200])
        return None


_PROCEDURE_COMPOUND_PATTERNS = (
    re.compile(r"บ่อย(?:แค่ไหน|เท่าไหร่|มาก).*?(?:และ|กับ).*(?:ขั้นตอน|วิธี)", re.IGNORECASE),
    re.compile(r"(?:ขั้นตอน|วิธี).*?(?:และ|กับ).*?บ่อย(?:แค่ไหน|เท่าไหร่|มาก)", re.IGNORECASE),
)

# Single lookup-table rows (HWTO/EDM ON/OFF) — not multi-hop.
_SIGNAL_STATE_PATTERN = re.compile(
    r"\b(?:ON|OFF)\b.*?(?:และ|แต่|,).*?\b(?:ON|OFF|EDM|output)\b",
    re.IGNORECASE,
)


# Domain vocabularies for cross-domain multi-topic detection. A single question
# that touches BOTH a machinery/technical topic AND an HR/welfare/policy topic
# (e.g. "servo overheat กี่องศา แล้วบริษัทจ่ายเงินเดือนเป็นอะไร") embeds to a
# vector dominated by one domain and silently drops the other — decompose so
# each domain is retrieved on its own.
_MACHINERY_TERMS = (
    "servo", "motor", "มอเตอร์", "alarm", "อะไหล่", "เครื่องจักร", "overheat",
    "แรงดัน", "อุณหภูมิ", "เซ็นเซอร์", "sensor", "plc", "wiring", "ไดรเวอร์",
    "driver", "jogging", "โหมด", "spindle", "เกียร์", "รหัส", "error", "รอบ",
    "ร้อน", "เครื่องร้อน",
)
_WELFARE_TERMS = (
    "สวัสดิการ", "เงินเดือน", "โบนัส", "ลาป่วย", "ลากิจ", "ลาพักร้อน", "วันลา",
    "เวลาทำงาน", "พนักงาน", "hr", "welfare", "payroll", "นโยบายบริษัท", "ค่าจ้าง",
    "ประกัน", "กองทุน", "บริษัทจ่าย",
)


def _spans_two_domains(q_lower: str) -> bool:
    has_machinery = any(t in q_lower for t in _MACHINERY_TERMS)
    has_welfare = any(t in q_lower for t in _WELFARE_TERMS)
    return has_machinery and has_welfare


def should_attempt_decomposition(question: str) -> bool:
    """Heuristic: only attempt decomposition for likely multi-hop questions."""
    q = question.strip()
    if any(pattern.search(q) for pattern in _PROCEDURE_COMPOUND_PATTERNS):
        return False
    if _SIGNAL_STATE_PATTERN.search(q):
        return False
    machines = _has_machine_ids(q)
    if len(machines) >= 2:
        return True
    if len(q) < 30:
        return False
    q_lower = q.lower()
    # Cross-domain question (machinery + welfare/policy) — split so both are found.
    if _spans_two_domains(q_lower):
        return True
    # Do not split on bare "และ"/"กับ" — e.g. frequency + steps in one manual section.
    multi_signals = ["เทียบ", "compared", "vs", "แล้วถ้า", "แต่ถ้า", "what if"]
    return any(signal in q_lower for signal in multi_signals)


async def decompose_query(question: str) -> DecomposedQuery | None:
    """Decompose a question into sub-queries if it's multi-hop.

    Returns None if the question is atomic (no decomposition needed).
    """
    if not should_attempt_decomposition(question):
        return None

    rules_result = _rules_decompose(question)
    if rules_result:
        log.info(
            "query_decomposed",
            strategy=rules_result.strategy,
            sub_count=len(rules_result.sub_queries),
        )
        return rules_result

    llm_result = await _llm_decompose(question)
    if llm_result:
        log.info(
            "query_decomposed",
            strategy=llm_result.strategy,
            sub_count=len(llm_result.sub_queries),
        )
        return llm_result

    return None
