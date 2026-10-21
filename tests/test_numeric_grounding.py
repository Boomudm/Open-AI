"""Tests for numeric grounding v2 (Phase 9)."""

from __future__ import annotations

import uuid

from spark.generation.citations import validate_grounded_citations
from spark.retrieval.models import RetrievedDoc
from spark.generation.numeric import (
    answer_numerics_subset_of_context,
    extract_numerics,
    mask_document_locators,
)


def test_extract_numerics_parses_temperature_variants() -> None:
    tokens = extract_numerics("Temperature exceeds 80°C and 80 C.")
    values = {(round(t.value), t.unit) for t in tokens}
    assert (80, "c") in values


def test_extract_numerics_normalizes_thousands_separator() -> None:
    tokens = extract_numerics("Load capacity 5,000 kg")
    assert any(t.value == 5000.0 for t in tokens)


def test_answer_numerics_rejects_hallucinated_temperature() -> None:
    context = "WARNING: Check cooling fan if temperature exceeds 80°C."
    answer = "Check cooling fan if temperature exceeds 85°C."
    assert answer_numerics_subset_of_context(answer, context) is False
    assert answer_numerics_subset_of_context(
        "Check cooling fan if temperature exceeds 80°C.",
        context,
    )


def test_page_references_are_not_numeric_claims() -> None:
    # Real suppression case (17 Jul): a correct LED answer opened with
    # "จากคู่มือ Oriental Servo Driver หน้า 21 และ 53" and pointed at
    # "(หน้า 71)". Those page numbers come from chunk METADATA, never chunk
    # text, so the gate replaced the whole correct answer with no_data.
    context = "PWR/ALM LED lights green while the control power supply is on."
    answer = (
        "จากคู่มือ Oriental Servo Driver หน้า 21 และ 53\n"
        "PWR/ALM LED ติดสว่างสีเขียวขณะเปิดจ่ายไฟควบคุม (ดูหัวข้อ 5.3 หน้า 71)"
    )
    assert answer_numerics_subset_of_context(answer, context) is True


def test_locator_masking_keeps_value_claims_enforced() -> None:
    # Masking "หน้า 53" must not let a fabricated measurement through.
    context = "Threshold is 80°C (see manual)."
    answer = "ค่าเกณฑ์คือ 85°C ตามหน้า 53"
    assert answer_numerics_subset_of_context(answer, context) is False


def test_mask_document_locators_patterns() -> None:
    masked = mask_document_locators(
        "ดูตาราง 2-4 หน้า 148 และ 150, section 5.3, p. 72, pages 10-12"
    )
    assert "148" not in masked
    assert "150" not in masked
    assert "5.3" not in masked
    assert "72" not in masked
    assert "10" not in masked
    # Non-locator numbers survive.
    assert "85" in mask_document_locators("อุณหภูมิ 85°C ที่หน้า 21")


def test_validate_grounded_citations_rejects_wrong_numeric() -> None:
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Temperature exceeds 80°C.",
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
            "page": 1,
        },
    )
    ok, _ = validate_grounded_citations(
        f"อุณหภูมิเกิน 85°C [chunk_id:{chunk_id}]",
        [doc],
    )
    assert ok is False

    ok2, cited = validate_grounded_citations(
        f"อุณหภูมิเกิน 80°C [chunk_id:{chunk_id}]",
        [doc],
    )
    assert ok2 is True
    assert cited == [doc]


def test_question_numerics_are_not_fabrications() -> None:
    """A number the USER wrote in the question ("45 cSt") is not a
    hallucination when the answer restates it — suppressing the whole answer
    over it produced false no-data."""
    from spark.generation.numeric import answer_numerics_subset_of_context

    answer = "เอกสารไม่ได้ระบุเกณฑ์ความหนืด 45 cSt โดยตรง แต่ระบุรอบเปลี่ยนถ่ายทุก 500 hours"
    context = "Change gear oil every 500 hours."
    question = "ถ้าน้ำมันเกียร์มีความหนืดต่ำกว่า 45 cSt ยังใช้งานต่อได้ไหม"
    # without the question the restated 45 fails grounding
    assert answer_numerics_subset_of_context(answer, context) is False
    # with the question it is allowed
    assert answer_numerics_subset_of_context(answer, context, question=question) is True


def test_question_whitelist_excluded_for_safety_and_limit_questions() -> None:
    """Echoing the asker's number on limit/safety questions stays blocked —
    'สูงสุด 95 ใช่ไหม' answered 'ใช่ครับ 95' is confirmation bias. That includes
    comparative threshold-confirmation phrasings ('ต่ำกว่า 45 cSt ใช้ต่อได้ไหม'):
    the 30-question rerun showed the model confirming the asker's 45 off a KUKA
    page-number match. Non-threshold questions keep the whitelist ('error 5436
    แก้ยังไง' may restate 5436)."""
    from spark.generation.citations import _numeric_whitelist_question

    assert _numeric_whitelist_question("MC-001 อุณหภูมิสูงสุดที่อนุญาต 95 องศาใช่ไหม") is None
    assert _numeric_whitelist_question("ขั้นตอน LOTO ก่อนซ่อม MC-001") is None
    assert (
        _numeric_whitelist_question("ถ้าน้ำมันเกียร์หนืดต่ำกว่า 45 cSt ใช้ต่อได้ไหม")
        is None
    )
    assert _numeric_whitelist_question("แรงดันเกิน 6 bar ยังใช้ได้ไหม") is None
    assert _numeric_whitelist_question("วิธีแก้ error 5436 ทำยังไง") is not None
    # comparative WITHOUT a number is not a threshold confirmation
    assert _numeric_whitelist_question("มอเตอร์ร้อนเกินไป เกิดจากอะไร") is not None
