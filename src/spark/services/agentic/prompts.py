"""Prompt templates for agentic multi-tool synthesis."""

from __future__ import annotations

AGENTIC_SYNTHESIS_SYSTEM = """คุณคือผู้ช่วยด้านเอกสารโรงงาน ตอบเป็นภาษาไทยเสมอ \
อ้างอิงแหล่งข้อมูลในรูปแบบ [ชื่อไฟล์ หน้า n] หรือ [ตาราง แถว n] \
ห้ามแต่งตัวเลขที่ไม่มีในเอกสาร"""

AGENTIC_SYNTHESIS_HUMAN = """คำถาม: {question}

=== ผลจากเอกสาร (search_documents) ===
{rag_context}

=== ผลจากฐานข้อมูล (query_database) ===
{sql_context}

รวมข้อมูลจากทั้งสองแหล่ง (ถ้ามี) เป็นคำตอบภาษาไทยเดียว พร้อมอ้างอิงแหล่งที่มา"""


def build_synthesis_human_prompt(
    *,
    question: str,
    rag_context: str,
    sql_context: str,
) -> str:
    return AGENTIC_SYNTHESIS_HUMAN.format(
        question=question.strip(),
        rag_context=rag_context.strip() or "(ไม่มีข้อมูลจากเอกสาร)",
        sql_context=sql_context.strip() or "(ไม่มีข้อมูลจากฐานข้อมูล)",
    )
