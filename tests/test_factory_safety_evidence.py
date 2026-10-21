"""Cross-lingual evidence gate for safety / status manual lookups (F-02 style)."""

from __future__ import annotations

from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.preprocess.decompose import should_attempt_decomposition
from spark.retrieval.scoring import _has_sufficient_evidence


def _manual(text: str, *, source_file: str = "KSS_Manual.pdf", page: int = 1) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.72,
        vector_score=0.72,
        payload={
            "document_type": "machine_manual",
            "source_file": source_file,
            "page": page,
            "chunk_id": f"test-chunk-{page}",
        },
    )


def test_enabling_switch_thai_question_passes_english_manual_evidence() -> None:
    q = "ต้องทดสอบ enabling switch บ่อยแค่ไหน และมีขั้นตอนทดสอบยังไง"
    doc = _manual(
        "Function test: test the enabling switch at least once every 12 months.",
        page=35,
    )
    assert _has_sufficient_evidence(q, RAGFilter(machine_id="MC-01"), [doc]) is True


def test_hwto_edm_state_table_passes_evidence() -> None:
    q = "ถ้า HWTO1 ON แต่ HWTO2 OFF และ EDM output OFF หมายความว่าเกิดอะไรขึ้น"
    doc = _manual(
        "HWTO1 input HWTO2 input EDM output ON OFF OFF "
        "An alarm of emergency stop circuit error is generated.",
        source_file="Oriental_Servo_Manual.pdf",
        page=72,
    )
    assert _has_sufficient_evidence(q, RAGFilter(machine_id="MC-01"), [doc]) is True


def test_system_board_led_red_passes_evidence() -> None:
    q = "ถ้า LED บน system board ติดสีแดง หมายความว่าอย่างไร"
    doc = _manual(
        "There are LEDs on the system board which light up red in the event of a fault.",
        page=193,
    )
    assert _has_sufficient_evidence(q, RAGFilter(machine_id="MC-01"), [doc]) is True


def test_procedure_compound_question_not_decomposed() -> None:
    q = "ต้องทดสอบ enabling switch บ่อยแค่ไหน และมีขั้นตอนทดสอบยังไง"
    assert should_attempt_decomposition(q) is False


def test_hwto_signal_state_question_not_decomposed() -> None:
    q = "ถ้า HWTO1 ON แต่ HWTO2 OFF และ EDM output OFF หมายความว่าเกิดอะไรขึ้น"
    assert should_attempt_decomposition(q) is False


def test_cross_lingual_extractive_allowed_when_translation_unavailable() -> None:
    from spark.generation.extractive import format_extractive_answer
    import asyncio

    q = "ต้องทดสอบ enabling switch บ่อยแค่ไหน และมีขั้นตอนทดสอบยังไway"
    doc = _manual(
        "The test must be carried out at least once every 12 months. "
        "Press the enabling switch for 3 seconds.",
        page=35,
    )

    async def _run() -> tuple[str, list] | None:
        return await format_extractive_answer(q, [doc], translate=False)

    result = asyncio.run(_run())
    assert result is not None
    answer, cited = result
    assert "enabling switch" in answer.lower()
    assert cited
