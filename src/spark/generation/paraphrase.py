"""Locked-span paraphrase generation (Phase 10)."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.generation.evidence_spans import EvidenceSpan

log = get_logger(__name__)


async def paraphrase_locked_spans(
    llm: Any,
    question: str,
    spans: list[EvidenceSpan],
) -> str:
    locked = "\n".join(f"- [chunk_id:{span.chunk_id}] {span.text}" for span in spans)
    messages = [
        SystemMessage(
            content=(
                "เรียบเรียงข้อความหลักฐานที่ล็อกไว้ให้เป็นภาษาไทยที่อ่านง่าย "
                "สำหรับช่างซ่อมบำรุงในโรงงาน โดยยึดกติกาต่อไปนี้อย่างเคร่งครัด:\n"
                "1. ใช้เฉพาะข้อเท็จจริงที่อยู่ในข้อความที่ล็อกไว้เท่านั้น "
                "ห้ามเพิ่มตัวเลข ขั้นตอน คำเตือน หรือคำอธิบายของตัวเอง\n"
                "2. ตัวเลข หน่วย รหัสอะไหล่ ชื่อรุ่น ชื่อสัญญาณ/แท็ก (เช่น RES0.xxx, CN7, AWG24) "
                "คงไว้ตามต้นฉบับทุกตัวอักษร ห้ามแปลหรือสะกดใหม่\n"
                "3. ตอบให้ตรงคำถามก่อนในประโยคแรก แล้วค่อยให้รายละเอียด\n"
                "4. ถ้าเนื้อหาเป็นรายการหรือขั้นตอน ให้จัดเป็นข้อ (1. 2. 3. หรือ -) "
                "ประโยคสั้น อ่านแล้วนำไปใช้หน้างานได้ทันที\n"
                "5. ทุกประโยคที่มีสาระต้องลงท้ายด้วย [chunk_id:...] ของข้อความที่ใช้ "
                "ประโยคใดอ้างอิงไม่ได้ให้ตัดทิ้ง"
            )
        ),
        HumanMessage(content=f"คำถาม: {question}\n\nข้อความที่ล็อกแล้ว:\n{locked}"),
    ]
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=settings.rag_llm_timeout_sec,
        )
        raw = response.content if hasattr(response, "content") else str(response)
        return str(raw or "").strip()
    except Exception as exc:
        log.warning("paraphrase_locked_spans_failed", error=str(exc)[:200])
        return ""
