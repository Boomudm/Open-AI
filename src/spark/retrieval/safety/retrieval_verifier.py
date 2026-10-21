"""Corrective RAG (CRAG) — verify retrieval relevance before generation.

After retrieval but before generation, verifies that top documents actually
answer the question. If relevance is low, triggers corrective actions:
1. Query refinement + re-retrieval
2. Scope broadening
3. Honest "insufficient evidence" instead of hallucinated answers

Based on: Yan et al. "Corrective Retrieval Augmented Generation" (2024).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from spark.core.logging import get_logger
from spark.retrieval.models import RetrievedDoc

log = get_logger(__name__)

CRAGAction = Literal["accept", "refine", "reject"]

_VERIFY_PROFILE = "tagging"

_RELEVANCE_PROMPT = (
    "คุณเป็นผู้ตรวจสอบความเกี่ยวข้องของเอกสาร สำหรับระบบค้นหาโรงงาน\n"
    "ให้คำถามและเอกสารที่ค้นพบ ตัดสินว่าเอกสารมีข้อมูลที่ตอบคำถามได้หรือไม่\n"
    "ตอบด้วยคำเดียว:\n"
    "- RELEVANT: เอกสารมีข้อมูลที่ตอบคำถามได้โดยตรง\n"
    "- PARTIAL: เอกสารมีข้อมูลบางส่วนที่เกี่ยวข้อง\n"
    "- IRRELEVANT: เอกสารไม่เกี่ยวข้องกับคำถามเลย"
)


@dataclass(frozen=True)
class VerificationResult:
    action: CRAGAction
    relevant_docs: list[RetrievedDoc]
    relevant_count: int
    partial_count: int
    irrelevant_count: int
    confidence: float


async def _verify_doc_relevance(question: str, doc: RetrievedDoc) -> str:
    """LLM-based relevance verification for a single document."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from spark.core.llm_client import get_chat_llm

    content = (doc.page_content or "")[:800]
    if not content.strip():
        return "IRRELEVANT"

    try:
        llm = get_chat_llm(_VERIFY_PROFILE)
        messages = [
            SystemMessage(content=_RELEVANCE_PROMPT),
            HumanMessage(content=f"คำถาม: {question[:300]}\n\nเอกสาร:\n{content}"),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=5.0)
        verdict = str(getattr(response, "content", response) or "").strip().upper()

        if "RELEVANT" in verdict and "IRRELEVANT" not in verdict:
            return "RELEVANT"
        if "PARTIAL" in verdict:
            return "PARTIAL"
        return "IRRELEVANT"
    except Exception as exc:
        log.warning("crag_verify_failed", error=str(exc)[:200])
        return "PARTIAL"


def _fast_relevance_check(question: str, doc: RetrievedDoc) -> str:
    """Fast heuristic relevance check without LLM."""
    import re
    from spark.retrieval.exact import exact_evidence_terms
    from spark.retrieval.intent.glossary import expand_lexical_variants

    content = (doc.page_content or "").lower()
    expanded_question = expand_lexical_variants(question)
    exact_terms = list(doc.payload.get("exact_terms") or exact_evidence_terms(question))
    if any(str(term or "").strip().lower() in content for term in exact_terms if len(str(term or "").strip()) >= 3):
        return "RELEVANT"

    q_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", expanded_question.lower()))
    if not q_tokens:
        return "PARTIAL"

    c_tokens = set(re.findall(r"[a-zA-Z0-9฀-๿]{3,}", content))
    overlap = len(q_tokens & c_tokens) / max(len(q_tokens), 1)
    q_numbers = set(re.findall(r"\d+(?:\.\d+)?", question.lower()))
    c_numbers = set(re.findall(r"\d+(?:\.\d+)?", content))
    domain_units = {"bar", "psi", "rpm", "mpa", "nm", "kw", "kg", "mm"}
    has_domain_unit = bool(q_tokens & domain_units or c_tokens & domain_units)
    thermal_question = (
        bool({"ร้อน", "อุณหภูมิ", "temperature", "temp", "overheat"} & q_tokens)
        or "ร้อน" in question.lower()
        or "อุณหภูมิ" in question.lower()
    )
    thermal_content = bool({"temperature", "temp", "overheat", "cooling", "fan"} & c_tokens) or "°c" in content

    if overlap >= 0.4 or (overlap >= 0.25 and has_domain_unit):
        return "RELEVANT"
    if thermal_question and thermal_content:
        return "RELEVANT"
    if q_numbers and q_numbers & c_numbers:
        return "RELEVANT"
    if overlap >= 0.15:
        return "PARTIAL"
    return "IRRELEVANT"


async def verify_retrieval(
    question: str,
    docs: list[RetrievedDoc],
    *,
    use_llm: bool = True,
    max_verify: int = 5,
) -> VerificationResult:
    """Verify top retrieved documents for relevance (CRAG pattern).

    Returns a VerificationResult with the recommended action:
    - accept: enough relevant docs, proceed to generation
    - refine: some relevant docs but need more, try re-retrieval
    - reject: no relevant docs, return honest "no data" answer
    """
    if not docs:
        return VerificationResult(
            action="reject",
            relevant_docs=[],
            relevant_count=0,
            partial_count=0,
            irrelevant_count=0,
            confidence=0.0,
        )

    to_verify = docs[:max_verify]
    verdicts: list[tuple[RetrievedDoc, str]] = []

    if use_llm:
        sem = asyncio.Semaphore(3)

        async def check(doc: RetrievedDoc) -> tuple[RetrievedDoc, str]:
            async with sem:
                verdict = await _verify_doc_relevance(question, doc)
                return doc, verdict

        results = await asyncio.gather(*(check(d) for d in to_verify))
        verdicts = list(results)
    else:
        verdicts = [(d, _fast_relevance_check(question, d)) for d in to_verify]

    relevant = [d for d, v in verdicts if v == "RELEVANT"]
    partial = [d for d, v in verdicts if v == "PARTIAL"]
    irrelevant = [d for d, v in verdicts if v == "IRRELEVANT"]

    remaining = [d for d in docs[max_verify:]]
    usable_docs = relevant + partial + remaining

    relevant_count = len(relevant)
    partial_count = len(partial)
    irrelevant_count = len(irrelevant)
    total = len(verdicts)

    relevance_ratio = (relevant_count + 0.5 * partial_count) / max(total, 1)

    if relevant_count >= 2 or (relevant_count >= 1 and partial_count >= 1):
        action: CRAGAction = "accept"
    elif relevant_count >= 1 or partial_count >= 2:
        action = "refine"
    elif partial_count == 1 and len(docs) == 1 and float(docs[0].score or 0.0) >= 0.75:
        action = "refine"
    else:
        action = "reject"

    log.info(
        "crag_verification",
        action=action,
        relevant=relevant_count,
        partial=partial_count,
        irrelevant=irrelevant_count,
        confidence=round(relevance_ratio, 3),
    )

    return VerificationResult(
        action=action,
        relevant_docs=usable_docs,
        relevant_count=relevant_count,
        partial_count=partial_count,
        irrelevant_count=irrelevant_count,
        confidence=round(relevance_ratio, 4),
    )
