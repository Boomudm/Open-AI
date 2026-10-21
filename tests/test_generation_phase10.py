"""Phase 10 — grounding and generation hardening."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.core.config import settings
from spark.generation.citations import validate_grounded_citations
from spark.generation.evidence_spans import select_evidence_spans
from spark.generation.numeric import answer_numerics_subset_of_context, extract_numerics
from spark.generation.pipeline import generate
from spark.generation.thai_enforce import answer_fails_thai_policy
from spark.generation.types import GenerationInput
from spark.schemas.rag import sources_to_refs
from spark.services.qa_cache_service import QACacheService
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RetrievedDoc, cited_docs_to_sources


def _doc(
    text: str,
    *,
    chunk_id: str | None = None,
    document_type: str = "sop",
) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id or str(uuid.uuid4()),
            "document_type": document_type,
            "source_file": "sop.pdf",
            "page": 1,
        },
    )


class FakeLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def ainvoke(self, _payload):
        class Response:
            pass

        resp = Response()
        resp.content = self._answer
        return resp


def test_citation_validator_allows_documented_multi_mode_values() -> None:
    # Both values appear in the chunk's own text (mode-dependent spec), so
    # quoting the pair is faithful reporting, not a contradiction — wiring and
    # spec tables legitimately hold many same-unit values (16 Jul demo-QA fix).
    doc = _doc("Operating pressure 5 bar or 7 bar depending on mode.")
    cid = doc.payload["chunk_id"]
    ok, _ = validate_grounded_citations(
        f"ความดัน 5 bar และ 7 bar [chunk_id:{cid}]",
        [doc],
    )
    assert ok is True


def test_citation_validator_rejects_same_unit_value_absent_from_chunk() -> None:
    doc = _doc("Operating pressure 5 bar or 7 bar depending on mode.")
    cid = doc.payload["chunk_id"]
    ok, _ = validate_grounded_citations(
        f"ความดัน 5 bar และ 9 bar [chunk_id:{cid}]",
        [doc],
    )
    assert ok is False


def test_citation_validator_allows_multiple_numbers_without_unit() -> None:
    doc = _doc("2024-01-15,MC-001,เปลี่ยนลูกปืน,completed")
    cid = doc.payload["chunk_id"]
    ok, cited = validate_grounded_citations(
        f"[chunk_id:{cid}] 2024-01-15,MC-001,เปลี่ยนลูกปืน,completed.",
        [doc],
    )
    assert ok is True
    assert cited == [doc]


    doc = _doc("LOTO: isolate energy before maintenance.")
    orphan = str(uuid.uuid4())
    ok, cited = validate_grounded_citations(
        f"ต้องทำ LOTO ก่อนซ่อม [chunk_id:{orphan}]",
        [doc],
    )
    assert ok is False
    assert cited == []


def test_citation_validator_rejects_mostly_uncited_sentences() -> None:
    doc = _doc("Pressure limit 5 bar.")
    cid = doc.payload["chunk_id"]
    answer = (
        f"ความดันสูงสุด 5 bar [chunk_id:{cid}]. "
        "ประโยคที่สองไม่มี citation. "
        "ประโยคที่สามไม่มี citation. "
        "ประโยคที่สี่ไม่มี citation."
    )
    ok, _ = validate_grounded_citations(answer, [doc])
    assert ok is False


def test_numeric_hallucination_rejected_by_validator() -> None:
    doc = _doc("Temperature must not exceed 80°C during operation.")
    cid = doc.payload["chunk_id"]
    ok, _ = validate_grounded_citations(
        f"อุณหภูมิต้องไม่เกิน 85°C [chunk_id:{cid}]",
        [doc],
    )
    assert ok is False


def test_thai_numerals_and_bar_unit_grounding() -> None:
    context = "ความดันสูงสุด ๕ บาร์ ระหว่างทดสอบ"
    assert answer_numerics_subset_of_context("ความดัน ๕ บาร์", context) is True
    assert answer_numerics_subset_of_context("ความดัน ๖ บาร์", context) is False
    tokens = extract_numerics("ความดัน ๕ บาร์")
    assert any(round(t.value) == 5 and t.unit == "bar" for t in tokens)


@pytest.mark.asyncio
async def test_grounded_llm_numeric_hallucination_returns_no_data(monkeypatch) -> None:
    doc = _doc("Maximum temperature 80°C.")
    cid = doc.payload["chunk_id"]
    monkeypatch.setattr(
        "spark.generation.extractive.format_extractive_answer",
        AsyncMock(return_value=None),
    )
    inp = GenerationInput(
        question="อุณหภูมิสูงสุดเท่าไร",
        docs=[doc],
        llm=FakeLLM(f"สูงสุด 85°C [chunk_id:{cid}]"),
        force_extractive_first=False,
    )
    from spark.generation import grounded_llm

    result = await grounded_llm.run_grounded_llm(inp)
    assert result.answer == NO_DATA_ANSWER
    assert result.answer_path == "numeric_grounding_fail"


@pytest.mark.asyncio
async def test_safety_questions_use_structured_grounded_llm_not_extractive(
    monkeypatch,
) -> None:
    loto_doc = _doc(
        "LOTO procedure: 1) Notify supervisor 2) Shut down machine 3) Isolate energy "
        "4) Apply lock and tag 5) Verify zero energy before maintenance.",
        document_type="sop",
    )
    cid = loto_doc.payload["chunk_id"]

    async def fake_structured_safety(_inp: GenerationInput):
        from spark.generation.types import GroundedGenerateResult

        return GroundedGenerateResult(
            answer=f"1. ตัดพลังงานและตรวจสอบพลังงานเป็นศูนย์ [chunk_id:{cid}]",
            cited_docs=[loto_doc],
            answer_path="grounded_structured_safety",
            citations_verified=True,
            generation_mode="grounded_llm",
        )

    monkeypatch.setattr(
        "spark.generation.pipeline.run_constrained_safety",
        fake_structured_safety,
    )
    monkeypatch.setattr(
        "spark.generation.pipeline.apply_nli_gate",
        lambda _question, result, **kwargs: result,
    )
    inp = GenerationInput(
        question="ขั้นตอน LOTO ก่อนซ่อมเครื่องต้องทำอะไร",
        docs=[loto_doc],
        llm=FakeLLM("ไม่ควรถูกใช้เมื่อ structured safety สำเร็จ"),
        force_extractive_first=True,
    )
    out = await generate(inp)
    assert out.result.answer_path == "grounded_structured_safety"
    assert out.result.generation_mode == "grounded_llm"
    assert out.result.citations_verified is True


@pytest.mark.asyncio
async def test_thai_question_gets_thai_grounded_llm_answer(monkeypatch) -> None:
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    cid = doc.payload["chunk_id"]
    inp = GenerationInput(
        question="Servo MC-001 ร้อนผิดปกติต้องทำอย่างไร",
        docs=[doc],
        llm=FakeLLM(f"ตรวจสอบพัดลมระบายความร้อนเมื่ออุณหภูมิเกิน 80°C [chunk_id:{cid}]"),
        force_extractive_first=True,
    )
    out = await generate(inp)
    assert out.result.citations_verified is True
    assert out.result.answer_path == "grounded_llm"
    assert out.result.generation_mode == "grounded_llm"
    assert not answer_fails_thai_policy(inp.question, out.result.answer)


@pytest.mark.asyncio
async def test_same_language_unsupported_cited_claims_are_flagged_unverified() -> None:
    from spark.retrieval.constants import UNVERIFIED_ANSWER_SUFFIX

    doc = _doc("Warranty period is 24 months from delivery.", document_type="machine_manual")
    cid = doc.payload["chunk_id"]
    inp = GenerationInput(
        question="What is covered by the controller warranty?",
        docs=[doc],
        llm=FakeLLM(
            "The controller is waterproof for outdoor washdown. "
            f"It includes free replacement filters [chunk_id:{cid}]."
        ),
        force_extractive_first=False,
    )
    out = await generate(inp)
    assert out.result.answer_path == "grounded_unverified"
    assert out.result.citations_verified is False
    assert out.result.answer.endswith(UNVERIFIED_ANSWER_SUFFIX)


def test_evidence_spans_include_offsets() -> None:
    text = "LOTO: isolate all energy sources before opening guard."
    doc = _doc(text)
    spans = select_evidence_spans("LOTO before repair", [doc])
    assert spans
    span = spans[0]
    assert span.start_offset >= 0
    assert span.end_offset > span.start_offset
    assert text[span.start_offset : span.end_offset].strip()


def test_sources_to_refs_carries_span_offsets() -> None:
    doc = _doc("LOTO step 1: notify supervisor.")
    sources = cited_docs_to_sources("LOTO steps", [doc])
    assert sources
    refs = sources_to_refs(sources)
    assert isinstance(refs[0].spans, list)


def test_sources_to_refs_carries_needs_review_flag() -> None:
    doc = _doc("Diagram page 3 (EE-07): belt servo wiring.")
    doc.payload["needs_review"] = True
    sources = cited_docs_to_sources("แบบไดอะแกรม EE-07", [doc])
    assert sources[0]["needs_review"] is True
    refs = sources_to_refs(sources)
    assert refs[0].needs_review is True


def test_sources_to_refs_needs_review_defaults_none() -> None:
    doc = _doc("Check cooling fan.")
    sources = cited_docs_to_sources("cooling fan", [doc])
    assert sources[0]["needs_review"] is None
    refs = sources_to_refs(sources)
    assert refs[0].needs_review is None


@pytest.mark.asyncio
async def test_qa_cache_miss_when_chunk_generation_changes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_embed_model", "nomic-embed-text")
    chunk_id = uuid.uuid4()
    sources = [
        {
            "chunk_id": str(chunk_id),
            "_cache_meta": {
                "chunk_snapshot_hash": "stored-hash",
                "embed_model_version": "nomic-embed-text",
            },
        }
    ]
    svc = QACacheService()
    db = AsyncMock()

    async def _new_hash(_db, _sources):
        return "current-hash-after-reingest"

    monkeypatch.setattr(
        "spark.services.qa_cache_service.chunk_snapshot_hash",
        _new_hash,
    )
    assert await svc._chunks_still_valid(db, sources, None) is False


@pytest.mark.asyncio
async def test_qa_cache_miss_when_embed_model_changes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_embed_model", "new-embed-model")
    sources = [
        {
            "chunk_id": str(uuid.uuid4()),
            "_cache_meta": {
                "chunk_snapshot_hash": "same-hash",
                "embed_model_version": "old-embed-model",
            },
        }
    ]
    svc = QACacheService()
    db = AsyncMock()
    assert await svc._chunks_still_valid(db, sources, None) is False
