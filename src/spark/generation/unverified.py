# -*- coding: utf-8 -*-
"""Flag-don't-suppress policy for grounded answers that miss a verification gate.

Production operation favors surfacing retrieved answers with a clear warning
over silently replacing them with NO_DATA. If retrieval found documents and the
LLM produced text, show the text and attach the retrieved docs as sources even
when citation coverage, self-verify, or numeric grounding checks are incomplete.

When the LLM itself returned nothing usable but retrieval *did* find documents,
we do NOT dump raw chunk markdown at the user (it is unreadable). Instead we make
one relaxed LLM pass to summarise the retrieved excerpts into readable prose and
attach a verify-me note. Only if the LLM is unavailable do we fall back to a
cleaned (de-markdowned) extract — never the raw table source.
"""

from __future__ import annotations

import asyncio
import re

from spark.core.logging import get_logger
from spark.generation.types import GroundedGenerateResult
from spark.retrieval.constants import NO_DATA_ANSWER, UNVERIFIED_ANSWER_SUFFIX
from spark.retrieval.models import RetrievedDoc

log = get_logger(__name__)

_CHUNK_CITATION_RE = re.compile(r"\[chunk_id:([^\]]+)\]", re.IGNORECASE)
_NO_DATA_RE = re.compile(
    r"(ไม่พบข้อมูล|ยังไม่พบข้อมูล|ไม่มีข้อมูล|ไม่พบคำตอบ|ยังไม่พบคำตอบ|"
    r"ไม่มีการระบุ|ไม่ได้ระบุ|no\s+data|not\s+found|"
    r"does\s+not\s+(?:contain|mention|specify))",
    re.IGNORECASE,
)

_RESUMMARIZE_SYSTEM = (
    "คุณคือ Neo วิศวกรซ่อมบำรุงอาวุโส ตอบเป็นภาษาไทยเท่านั้น แทนตัวเองว่า Neo และลงท้ายด้วยครับ\n"
    "หน้าที่ของคุณคือสรุปข้อมูลจากเอกสารที่ค้นพบด้านล่างให้ตอบคำถามอย่างอ่านเข้าใจง่าย เป็นย่อหน้าสั้นๆ\n"
    "- ห้ามแต่งข้อมูล ตัวเลข หรือค่าที่ไม่มีในเอกสาร ให้ยึดตามข้อความในเอกสารเท่านั้น\n"
    "- ถ้าเอกสารไม่ได้ตอบคำถามโดยตรง ให้สรุปว่าเอกสารที่พบกล่าวถึงอะไรที่พอเกี่ยวข้อง แล้วระบุว่ายังไม่พบคำตอบที่ตรงคำถาม\n"
    "- คงตัวเลข หน่วย รหัสอะไหล่ และชื่อรุ่นตามต้นฉบับทุกตัวอักษร"
)


def _has_valid_citation(answer: str, docs: list[RetrievedDoc]) -> bool:
    from spark.generation.citations import find_cited_ids

    cited = {c.lower() for c in find_cited_ids(answer or "")}
    if not cited:
        return False
    doc_ids = {str(d.payload.get("chunk_id") or "").strip().lower() for d in docs}
    return bool(cited & doc_ids)


_REFUSAL_BODY_MAX_CHARS = 250


def _is_refusal_only(answer: str) -> bool:
    """True when, citations and reference trailer aside, the answer just says
    "not found". Catches cited refusals that don't START with the refusal
    ("RES0.X ไม่ได้ระบุ... [chunk_id:...]"), which slip past prefix checks. A
    real answer carrying a side-note ("...เอกสารไม่ได้ระบุ Y เพิ่มเติม") is
    longer than the cap and stays usable."""
    body = _CHUNK_CITATION_RE.sub("", answer or "")
    body = re.sub(r"อ้างอิง:.*$", "", body, flags=re.DOTALL).strip()
    return bool(_NO_DATA_RE.search(body)) and len(body) <= _REFUSAL_BODY_MAX_CHARS


def _readable_extract_from_docs(docs: list[RetrievedDoc]) -> str:
    """LLM-free fallback: a cleaned, de-markdowned extract (never raw tables)."""
    for doc in docs:
        raw = doc.page_content or ""
        # Flatten markdown tables / pipes / separators into readable prose.
        text = re.sub(r"\|+", " ", raw)
        text = re.sub(r"-{2,}", " ", text)
        text = re.sub(r"#+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if len(text) > 500:
            text = text[:500].rstrip() + "…"
        title = str(doc.payload.get("title") or doc.payload.get("source_file") or "เอกสาร").strip()
        return (
            f"Neo พบข้อมูลที่อาจเกี่ยวข้องในเอกสาร **{title}** แต่ยังสรุปเป็นคำตอบที่ยืนยันได้ไม่ชัดเจนครับ\n\n"
            f"ใจความที่พบ: {text}"
        )
    return ""


async def _llm_resummarize(
    llm,
    question: str,
    docs: list[RetrievedDoc],
    chat_history: list[tuple[str, str]] | None,
) -> str | None:
    """One relaxed LLM pass that turns retrieved excerpts into readable prose."""
    if llm is None:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from spark.core.config import settings
        from spark.generation.context import build_grounded_context

        context = build_grounded_context(docs)
        if not context.strip():
            return None
        messages = [
            SystemMessage(content=_RESUMMARIZE_SYSTEM),
            HumanMessage(content=f"คำถาม: {question}\n\nเอกสารที่ค้นพบ:\n{context}"),
        ]
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=float(getattr(settings, "rag_llm_timeout_sec", 90) or 90),
        )
        raw = response.content if hasattr(response, "content") else str(response)
        text = str(raw or "").strip()
        return text or None
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("unverified_resummarize_failed", error=str(exc)[:200])
        return None


async def _extractive_rescue(
    question: str | None,
    docs: list[RetrievedDoc],
    llm,
    chat_history: list[tuple[str, str]] | None,
) -> GroundedGenerateResult | None:
    """Deterministic extractive answer when spans cover the question; else None."""
    if not question or not docs:
        return None
    # The rescue exists for questions anchored on something specific enough to
    # verify in the evidence text: a specific identifier (PLC tag, serial,
    # connector code) or the manual's own Latin terminology quoted inside a
    # Thai question ("safe input", "voltage"). There the exact evidence span IS
    # the answer and a weak generator's "not found" must not win. Without any
    # anchor, extractive spans match loose tokens — a page number equal to a
    # number in the question, an unrelated table row — and dress irrelevant
    # excerpts up as an answer, which is worse than an honest no-data.
    try:
        from spark.retrieval.preprocess.compound import alarm_codes, question_identifiers

        # An alarm/error code anchors as hard as a PLC tag — the manual's alarm
        # table row containing it IS the answer, so a flaky generator's refusal
        # must not become a false no-data. Hex codes ("26h") never match the
        # identifier regex (digits-first), hence the separate extractor.
        anchors = question_identifiers(question) + alarm_codes(question)
    except Exception:  # pragma: no cover - defensive
        anchors = []
    try:
        from spark.retrieval.scoring import _GENERIC_LATIN_QUERY_TERMS, _literal_latin_terms

        topical = sorted(_literal_latin_terms(question) - _GENERIC_LATIN_QUERY_TERMS)
    except Exception:  # pragma: no cover - defensive
        topical = []
    # A single Latin word ("MDB", "cSt") is too loose to anchor on — it can
    # never satisfy the two-hit rule below, so don't even attempt the rescue.
    if not anchors and len(topical) < 2:
        return None
    try:
        from spark.generation.extractive import run_extractive_first
        from spark.generation.types import GenerationInput

        inp = GenerationInput(
            question=question,
            docs=list(docs),
            llm=llm,
            chat_history=chat_history,
        )
        result = await run_extractive_first(inp)
        answer_lower = (result.answer or "").lower()
        # An identifier hit anchors on its own; topical terms are looser, so
        # require at least two distinct hits before trusting the span over the
        # LLM's refusal.
        topical_hits = sum(1 for t in topical if t in answer_lower)
        anchored = any(a.lower() in answer_lower for a in anchors) or topical_hits >= 2
        if result.citations_verified and result.generation_mode != "no_data" and anchored:
            return result
    except Exception as exc:  # rescue must never break the failure path
        log.warning("extractive_rescue_failed", error=str(exc)[:200])
    return None


async def flag_or_suppress(
    answer: str,
    docs: list[RetrievedDoc],
    *,
    is_safety: bool,
    reason: str,
    llm=None,
    question: str | None = None,
    chat_history: list[tuple[str, str]] | None = None,
) -> GroundedGenerateResult:
    """Return a flagged-but-shown answer when retrieval found source docs.

    If the LLM produced usable text (even if a gate failed), show it plus the
    verify-me note. If the LLM returned nothing usable, re-summarise the docs via
    one relaxed LLM pass (readable), never a raw chunk dump.
    """
    # Idempotent under re-flagging: a result that already went through this
    # function carries the suffix — strip it so a second pass (e.g. self-verify
    # re-flagging an already-unverified answer) can't stack a duplicate warning.
    stripped = (answer or "").replace(UNVERIFIED_ANSWER_SUFFIX, "").strip()
    llm_said_no_data = bool(stripped) and bool(_NO_DATA_RE.search(stripped))
    has_citation = _has_valid_citation(stripped, docs)
    # A cited answer that merely notes "เอกสารไม่ได้ระบุ..." on the side is still
    # an answer — keep it flagged instead of resummarizing it away. But a
    # citation pinned onto a bare refusal ("RES0.X ไม่ได้ระบุ... [chunk_id:...]")
    # is still a refusal, not an answer.
    refusal_only = llm_said_no_data and (not has_citation or _is_refusal_only(stripped))
    # Showing the model's own prose as-is requires at least one citation that
    # resolves to a retrieved chunk. Without one there is nothing tying the text
    # to the evidence, and length is no substitute: a fluent uncited answer is
    # the exact shape of a model answering from world knowledge over irrelevant
    # retrieval ("how do I cook kaprao" → a recipe, sourced to the HR policy).
    # Such text falls through to the re-summarise pass below, which is bound to
    # the retrieved excerpts and says so when they don't answer the question.
    llm_produced_usable = (
        bool(stripped)
        and stripped != NO_DATA_ANSWER
        and not refusal_only
        and has_citation
    )

    if refusal_only:
        # The model read the retrieved documents and concluded they don't
        # answer the question. Before trusting that, try a deterministic
        # extractive answer — when evidence spans genuinely cover the question
        # (exact PLC tags, spec rows), the answer IS in the documents and a
        # weak generator's "not found" must not become a false no-data.
        rescued = await _extractive_rescue(question, docs, llm, chat_history)
        if rescued is not None:
            log.info("unverified_extractive_rescue", reason=reason)
            return rescued
        # Otherwise return a real no-data so the caller renders the helpful
        # no-data message (near-miss docs listed in text, no citation cards) —
        # re-summarising irrelevant excerpts would dress them up as an answer.
        log.info("unverified_llm_no_data", reason=reason)
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )

    if bool(docs) and not llm_produced_usable:
        resummarized = await _llm_resummarize(llm, question or "", docs, chat_history)
        stripped = (resummarized or _readable_extract_from_docs(docs)).strip()

    safe_to_show = bool(stripped) and stripped != NO_DATA_ANSWER and bool(docs)
    if not safe_to_show:
        # answer_path must be "no_data" (not the gate reason) so callers strip
        # source cards — a NO_DATA answer with citations attached reads as a
        # contradiction to the user.
        log.info("unverified_suppressed", reason=reason)
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
            generation_mode="no_data",
        )
    # Source cards must mirror the citations the shown text actually makes.
    # Attaching the whole retrieval set labels the answer with documents it
    # never used (a wiring-diagram answer carded as the KUKA manual); only
    # when the text carries no resolvable citation (re-summarised prose) do
    # all retrieved docs remain the honest attribution.
    from spark.generation.citations import find_cited_ids

    cited_ids = {c.lower() for c in find_cited_ids(stripped)}
    cited_in_answer = [
        d
        for d in docs
        if str(d.payload.get("chunk_id") or "").strip().lower() in cited_ids
    ]
    return GroundedGenerateResult(
        answer=stripped + UNVERIFIED_ANSWER_SUFFIX,
        cited_docs=cited_in_answer or list(docs),
        answer_path="grounded_unverified",
        citations_verified=False,
        generation_mode="grounded_unverified",
    )
