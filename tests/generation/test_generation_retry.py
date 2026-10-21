"""Regenerate-on-garbage + first-attempt hedge for the noisy remote gateway.

The KKU gateway (deepseek-v4-flash) non-deterministically returns, over the
SAME retrieved context: a grounded answer, a bare refusal, a 3-token degenerate
reply, or a whole-request stall (observed 1-in-6, burning the 90s budget).
These tests pin the recovery behavior for each face of that.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from spark.core.config import settings
from spark.generation.grounded_llm import _generation_retry_reason, run_grounded_llm
from spark.generation.types import GenerationInput
from spark.generation.unverified import flag_or_suppress
from spark.retrieval.constants import NO_DATA_ANSWER, UNVERIFIED_ANSWER_SUFFIX
from spark.retrieval.models import RetrievedDoc


def _doc(text: str, *, chunk_id: str | None = None) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id or str(uuid.uuid4()),
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
            "page": 1,
            "machine_id": "MC-001",
        },
    )


class SequenceLLM:
    """Returns queued answers in order; repeats the last one when exhausted."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.calls = 0

    async def ainvoke(self, _payload):
        class Response:
            pass

        idx = min(self.calls, len(self._answers) - 1)
        self.calls += 1
        resp = Response()
        resp.content = self._answers[idx]
        return resp


class StallThenAnswerLLM(SequenceLLM):
    """First call hangs (a gateway stall); later calls answer normally."""

    async def ainvoke(self, payload):
        first = self.calls == 0
        if first:
            self.calls += 1
            await asyncio.sleep(30)
        return await super().ainvoke(payload)


# --- retry triage -----------------------------------------------------------


def test_retry_reason_empty() -> None:
    assert _generation_retry_reason("") == "empty_response"
    assert _generation_retry_reason(None) == "empty_response"


def test_retry_reason_degenerate_short_uncited() -> None:
    assert _generation_retry_reason("ครับ") == "degenerate_response"


def test_retry_reason_short_but_cited_is_accepted() -> None:
    assert _generation_retry_reason("145±12 °C [chunk_id:abc]") is None


def test_retry_reason_bare_refusal() -> None:
    # A short refusal may triage as degenerate first — either way it retries.
    assert _generation_retry_reason("ไม่พบข้อมูลในเอกสารที่ค้นหาครับ") is not None
    long_refusal = (
        "ไม่พบข้อมูลเกี่ยวกับอุณหภูมิของเซอร์โวมอเตอร์ในเอกสารที่เปิดอยู่ตอนนี้ครับ "
        "กรุณาตรวจสอบเอกสารรุ่นอื่น"
    )
    assert _generation_retry_reason(long_refusal) == "refusal_only"


def test_retry_reason_real_answer_is_accepted() -> None:
    answer = (
        "หากอุณหภูมิเกิน 80°C ให้ตรวจสอบพัดลมระบายความร้อนและรีเซ็ตสัญญาณเตือน "
        "[chunk_id:abc123]"
    )
    assert _generation_retry_reason(answer) is None


def test_retry_reason_long_uncited_answer_is_accepted() -> None:
    # Long uncited text is a citation-gate problem (flag path), not a transport
    # artifact — it must not burn the retry call.
    answer = "ตรวจสอบพัดลมระบายความร้อน จากนั้นรีเซ็ตสัญญาณเตือนที่แผงควบคุมหลักของเครื่อง"
    assert _generation_retry_reason(answer) is None


# --- run_grounded_llm regenerate --------------------------------------------


@pytest.mark.asyncio
async def test_refusal_then_grounded_answer_recovers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_generation_retry_enabled", True)
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    cid = doc.payload["chunk_id"]
    llm = SequenceLLM(
        "ไม่พบข้อมูลในเอกสารครับ",
        f"หากอุณหภูมิเกิน 80°C ให้ตรวจสอบพัดลมระบายความร้อน [chunk_id:{cid}]",
    )
    result = await run_grounded_llm(
        GenerationInput(question="เครื่องร้อนเกินต้องทำอย่างไร", docs=[doc], llm=llm)
    )
    assert llm.calls == 2
    assert result.answer_path == "grounded_llm"
    assert result.citations_verified is True


@pytest.mark.asyncio
async def test_repeated_refusal_stays_no_data(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_generation_retry_enabled", True)
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    llm = SequenceLLM("ไม่พบข้อมูลในเอกสารครับ")
    result = await run_grounded_llm(
        GenerationInput(question="เครื่องร้อนเกินต้องทำอย่างไร", docs=[doc], llm=llm)
    )
    assert llm.calls == 2  # one retry spent, refusal repeated
    assert result.answer_path == "no_data"
    assert result.answer == NO_DATA_ANSWER


@pytest.mark.asyncio
async def test_retry_disabled_keeps_single_call(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_generation_retry_enabled", False)
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    llm = SequenceLLM("ไม่พบข้อมูลในเอกสารครับ")
    result = await run_grounded_llm(
        GenerationInput(question="เครื่องร้อนเกินต้องทำอย่างไร", docs=[doc], llm=llm)
    )
    assert llm.calls == 1
    assert result.answer_path == "no_data"


# --- first-attempt hedge -----------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_first_attempt_hedges_to_retry(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_generation_retry_enabled", True)
    monkeypatch.setattr(settings, "rag_llm_timeout_sec", 60.0)
    monkeypatch.setattr(settings, "rag_llm_hedge_timeout_sec", 0.2)
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    cid = doc.payload["chunk_id"]
    llm = StallThenAnswerLLM(
        f"หากอุณหภูมิเกิน 80°C ให้ตรวจสอบพัดลมระบายความร้อน [chunk_id:{cid}]",
    )
    started = time.perf_counter()
    result = await run_grounded_llm(
        GenerationInput(question="เครื่องร้อนเกินต้องทำอย่างไร", docs=[doc], llm=llm)
    )
    elapsed = time.perf_counter() - started
    assert result.answer_path == "grounded_llm"
    assert result.citations_verified is True
    assert elapsed < 10.0  # nowhere near the 30s stall


@pytest.mark.asyncio
async def test_hedge_skipped_when_budget_too_small(monkeypatch) -> None:
    # Below 60s there is no room for two attempts — the stall must surface as
    # the normal timeout path, not a hedge.
    monkeypatch.setattr(settings, "rag_generation_retry_enabled", True)
    monkeypatch.setattr(settings, "rag_llm_timeout_sec", 0.3)
    monkeypatch.setattr(settings, "rag_llm_hedge_timeout_sec", 0.1)
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    llm = StallThenAnswerLLM("unused [chunk_id:x]")
    result = await run_grounded_llm(
        GenerationInput(question="เครื่องร้อนเกินต้องทำอย่างไร", docs=[doc], llm=llm)
    )
    assert llm.calls == 1
    assert result.answer_path == "llm_unavailable"


# --- flag_or_suppress degenerate guard ---------------------------------------


@pytest.mark.asyncio
async def test_degenerate_reply_not_shown_flagged() -> None:
    # "ครับ ⚠️โปรดตรวจสอบ..." must never reach the user — a degenerate uncited
    # reply falls back to the readable extract of the retrieved docs.
    doc = _doc("WARNING: Check cooling fan if temperature exceeds 80°C.")
    result = await flag_or_suppress(
        "ครับ", [doc], is_safety=False, reason="citation_incomplete", llm=None
    )
    assert not result.answer.startswith("ครับ")
    assert result.answer_path in ("grounded_unverified", "no_data")


@pytest.mark.asyncio
async def test_short_cited_answer_stays_usable() -> None:
    doc = _doc("Thermostat trip point 145±12 °C.")
    cid = doc.payload["chunk_id"]
    short = f"145±12 °C [chunk_id:{cid}]"
    result = await flag_or_suppress(
        short, [doc], is_safety=False, reason="self_verify_fail", llm=None
    )
    assert result.answer_path == "grounded_unverified"
    assert result.answer == short + UNVERIFIED_ANSWER_SUFFIX
