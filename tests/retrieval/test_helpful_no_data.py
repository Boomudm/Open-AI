"""Helpful no-data messages — name what WAS found and suggest better searches."""

from __future__ import annotations

from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.no_data import build_no_data_answer, machine_filter_mismatch_answer


def test_machine_filter_mismatch_names_selected_and_mentioned_machines() -> None:
    answer = machine_filter_mismatch_answer(
        "ก่อนเริ่มเครื่อง MIX-01 ต้องตรวจอะไรบ้าง?",
        "AIR-01",
    )

    assert "AIR-01" in answer
    assert "MIX-01" in answer
    assert "เปลี่ยนเครื่อง" in answer


def _doc(title: str, machine_id: str | None = None) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="irrelevant content",
        score=0.1,
        vector_score=0.1,
        payload={
            "chunk_id": "c-1",
            "title": title,
            "source_file": f"{title}.pdf",
            "machine_id": machine_id,
        },
    )


def test_non_safety_message_lists_near_miss_docs_and_suggestions() -> None:
    docs = [_doc("Oriental Servo Manual", "MC-07"), _doc("Wiring Diagram Binder")]
    answer = build_no_data_answer(
        "มอเตอร์เสียงดังผิดปกติ", docs, rf=RAGFilter(factory_id="E-03")
    )
    assert answer != NO_DATA_ANSWER
    assert "Oriental Servo Manual" in answer
    assert "MC-07" in answer
    assert "คำแนะนำ" in answer
    # Thai question → suggest manual (English) terminology.
    assert "ภาษาอังกฤษ" in answer


def test_no_docs_still_gives_suggestions() -> None:
    answer = build_no_data_answer("วิธีทำผัดกะเพรา", [], rf=None)
    assert answer != NO_DATA_ANSWER
    assert "คำแนะนำ" in answer
    assert "ยังไม่พบข้อมูล" in answer


def test_safety_stays_terse_fail_closed() -> None:
    docs = [_doc("SOP Lockout")]
    answer = build_no_data_answer(
        "ขั้นตอน LOTO", docs, rf=None, is_safety=True
    )
    assert answer == NO_DATA_ANSWER


def test_machine_scoped_question_skips_machine_suggestion() -> None:
    answer = build_no_data_answer(
        "MC-07 น้ำมันรุ่นไหน", [], rf=RAGFilter(factory_id="E-03", machine_id="MC-07")
    )
    assert "ระบุรหัสเครื่องจักร เช่น" not in answer
