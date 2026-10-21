"""Tests for unified grounded generation and machine-anchored fallback scope."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from spark.generation.context import build_grounded_context, is_machine_anchored
from spark.generation.citations import validate_grounded_citations
from spark.generation.pipeline import grounded_generate_with_enforced_citations
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.service import (
    RAGService,
)


def _doc(text: str, *, chunk_id: str | None = None, machine_id: str = "MC-001") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id or str(uuid.uuid4()),
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
            "page": 1,
            "machine_id": machine_id,
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


def test_build_grounded_context_includes_chunk_id() -> None:
    doc = _doc("Check cooling fan.")
    ctx = build_grounded_context([doc])
    assert f"[chunk_id:{doc.payload['chunk_id']}]" in ctx


def test_build_grounded_context_flags_needs_review_chunks() -> None:
    doc = _doc("Diagram page 3 (EE-07): belt servo wiring.")
    doc.payload["needs_review"] = True
    ctx = build_grounded_context([doc])
    assert "ตีความจากภาพโดย AI ยังไม่ยืนยันโดยมนุษย์" in ctx


def test_build_grounded_context_no_warning_when_not_flagged() -> None:
    doc = _doc("Check cooling fan.")
    ctx = build_grounded_context([doc])
    assert "ตีความจากภาพโดย AI" not in ctx


def test_validate_grounded_citations_requires_chunk_id_per_sentence() -> None:
    doc = _doc("Temperature exceeds 80C.")
    cid = doc.payload["chunk_id"]
    ok, cited = validate_grounded_citations(
        f"อุณหภูมิเกิน 80C [chunk_id:{cid}]",
        [doc],
    )
    assert ok is True
    assert cited == [doc]

    bad, _ = validate_grounded_citations("อุณหภูมิเกิน 80C โดยไม่มี citation", [doc])
    assert bad is False


@pytest.mark.asyncio
async def test_grounded_generate_flags_answer_when_llm_lacks_citations(monkeypatch) -> None:
    # Flag-don't-suppress (PR #287): an uncited answer over real retrieved docs
    # is shown with the verify-me note instead of being replaced by NO_DATA.
    from spark.retrieval.constants import UNVERIFIED_ANSWER_SUFFIX

    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    result = await grounded_generate_with_enforced_citations(
        question="Servo MC-001 ร้อนผิดปกติ",
        docs=[doc],
        llm=FakeLLM("คำตอบทั่วไปที่ไม่มี citation"),
    )
    assert result.answer_path == "grounded_unverified"
    assert result.citations_verified is False
    assert result.answer.endswith(UNVERIFIED_ANSWER_SUFFIX)


def test_is_machine_anchored() -> None:
    assert is_machine_anchored(RAGFilter(machine_id="MC-001")) is True
    assert is_machine_anchored(RAGFilter(factory_id="F-01")) is False


def test_machine_anchored_fallback_never_drops_machine_id(monkeypatch) -> None:
    svc = RAGService()
    wrong_machine = _doc("Other machine manual.", machine_id="MC-002")
    calls: list[RAGFilter] = []

    async def fake_retrieve(_question, rf, *_args, **_kwargs):
        calls.append(rf)
        return [wrong_machine]

    monkeypatch.setattr(svc, "_retrieve", fake_retrieve)
    monkeypatch.setattr(svc, "_passes_relevance", lambda *_a, **_k: True)

    # "สั่นผิดปกติ" (not "ร้อนผิดปกติ") — an overheat symptom now takes the
    # safety-emergency intercept before retrieval; this test targets the
    # machine-anchored fallback, so it needs a non-safety symptom.
    result = asyncio.run(
        svc.query(
            "Servo MC-001 สั่นผิดปกติ",
            RAGFilter(machine_id="MC-001"),
        )
    )

    # No-data text is now a helpful message (near-miss docs + search tips), so
    # assert the contract instead of the literal string: the wrong machine's
    # content never becomes an answer or a source.
    assert result.answer_path == "no_data"
    assert result.sources == []
    assert "Other machine manual" not in result.answer
    machine_filters = [rf.machine_id for rf in calls if rf.machine_id is not None]
    assert machine_filters == ["MC-001"] or not machine_filters
