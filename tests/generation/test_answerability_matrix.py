"""Answerability evaluation matrix — diverse question types must produce
grounded, cited answers instead of refusals.

Runs the real generation + validation pipeline offline (fake LLM, pseudo
stream): direct factual, cross-lingual, numeric, summary bullets, table format,
comparison across documents, step-by-step, follow-up with history, short-format
request, and the empty-evidence fallback.
"""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.generation.pipeline import build_generation_input
from spark.generation.streaming import stream_grounded_answer
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RetrievedDoc


class FakeLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def ainvoke(self, _payload):
        class Response:
            content = self._answer

        return Response()


def _doc(chunk_id: str, content: str, source_file: str = "manual.pdf") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=content,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": "machine_manual",
            "source_file": source_file,
        },
    )


async def _run(question, docs, answer, chat_history=None, synthesis_question=None):
    inp = build_generation_input(
        question=question,
        docs=docs,
        llm=FakeLLM(answer),
        chat_history=chat_history,
        synthesis_question=synthesis_question,
        extractive_first=False,
    )
    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind == "done":
            final = event.result
    assert final is not None
    return final


@pytest.fixture(autouse=True)
def _pseudo_stream(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "spark_stream_live_tokens", False)


CID_A = str(uuid.uuid4())
CID_B = str(uuid.uuid4())


async def test_cross_lingual_factual_thai_question_english_doc() -> None:
    docs = [_doc(CID_A, "Main circuit overheat alarm triggers at 85 C.")]
    answer = f"เอกสารระบุว่า alarm ทำงานเมื่ออุณหภูมิถึง 85 องศาครับ [chunk_id:{CID_A}]"
    final = await _run("เครื่องร้อนเกินที่กี่องศา", docs, answer)
    assert final.answer_path != "no_data"
    assert final.citations_verified is True
    assert final.cited_docs


async def test_numeric_spec_question() -> None:
    docs = [_doc(CID_A, "Rated voltage 415 V. Rated current 6.4 A.")]
    answer = f"แรงดันไฟฟ้าที่กำหนดคือ 415 V และกระแส 6.4 A [chunk_id:{CID_A}]"
    final = await _run("แรงดันไฟฟ้าของเครื่องเท่าไหร่", docs, answer)
    assert final.citations_verified is True


async def test_summary_with_bullets_paragraph_citations() -> None:
    docs = [
        _doc(CID_A, "Chapter 1 covers installation. Chapter 2 covers wiring."),
        _doc(CID_B, "Chapter 3 covers alarm codes and maintenance schedules."),
    ]
    answer = (
        "## สรุปหัวข้อในคู่มือ\n"
        f"- การติดตั้งและการเดินสายไฟ อยู่ในบทที่ 1 และ 2 [chunk_id:{CID_A}]\n"
        f"- รหัส alarm และตารางบำรุงรักษา อยู่ในบทที่ 3 [chunk_id:{CID_B}]"
    )
    final = await _run("สรุปหัวข้อในคู่มือให้หน่อย", docs, answer)
    assert final.citations_verified is True
    assert len(final.cited_docs) == 2


async def test_table_format_request() -> None:
    docs = [_doc(CID_A, "Model X10 weight 25 kg. Model X20 weight 40 kg.")]
    answer = (
        "| รุ่น | น้ำหนัก | อ้างอิง |\n"
        "| --- | --- | --- |\n"
        f"| X10 | 25 kg | [chunk_id:{CID_A}] |\n"
        f"| X20 | 40 kg | [chunk_id:{CID_A}] |"
    )
    final = await _run("ทำตารางเทียบน้ำหนักแต่ละรุ่น", docs, answer)
    assert final.answer_path != "no_data"
    assert final.cited_docs


async def test_comparison_across_documents() -> None:
    docs = [
        _doc(CID_A, "Servo model A rated speed 3000 rpm.", "manual_a.pdf"),
        _doc(CID_B, "Servo model B rated speed 5000 rpm.", "manual_b.pdf"),
    ]
    answer = (
        f"รุ่น A มีความเร็ว 3000 rpm [chunk_id:{CID_A}]\n\n"
        f"ส่วนรุ่น B มีความเร็ว 5000 rpm ซึ่งเร็วกว่า [chunk_id:{CID_B}]"
    )
    final = await _run("เทียบความเร็วรุ่น A กับ B", docs, answer)
    assert final.citations_verified is True
    assert len(final.cited_docs) == 2


async def test_step_by_step_non_safety_procedure() -> None:
    docs = [_doc(CID_A, "Filter replacement: remove cover, swap filter, close cover.")]
    answer = (
        f"1. ถอดฝาครอบออก [chunk_id:{CID_A}]\n"
        f"2. เปลี่ยนไส้กรองใหม่ [chunk_id:{CID_A}]\n"
        f"3. ปิดฝาครอบให้แน่น [chunk_id:{CID_A}]"
    )
    final = await _run("วิธีเปลี่ยนไส้กรองทำยังไง", docs, answer)
    assert final.answer_path != "no_data"
    assert final.cited_docs


async def test_follow_up_with_chat_history() -> None:
    docs = [_doc(CID_A, "LED1 blinks 4 times on overheat alarm.")]
    history = [
        ("human", "เครื่องร้อนเกินที่กี่องศา"),
        ("ai", "85 องศาครับ"),
    ]
    answer = f"LED จะกระพริบ 4 ครั้งเมื่อเกิด alarm ครับ [chunk_id:{CID_A}]"
    final = await _run(
        "แล้ว LED กระพริบกี่ครั้ง",
        docs,
        answer,
        chat_history=history,
        synthesis_question="คำถามก่อนหน้า: เครื่องร้อนเกินที่กี่องศา\nคำถามต่อเนื่อง: แล้ว LED กระพริบกี่ครั้ง",
    )
    assert final.citations_verified is True


async def test_short_format_request() -> None:
    docs = [_doc(CID_A, "Recommended grease: Mobilith SHC 100.")]
    answer = f"Mobilith SHC 100 ครับ [chunk_id:{CID_A}]"
    final = await _run("ใช้จาระบีรุ่นไหน ตอบสั้นๆ", docs, answer)
    assert final.answer_path != "no_data"


async def test_no_evidence_returns_no_data_path() -> None:
    final = await _run("วิธีทำผัดกะเพรา", [], "irrelevant")
    assert final.answer_path == "no_data"
    assert final.answer == NO_DATA_ANSWER
