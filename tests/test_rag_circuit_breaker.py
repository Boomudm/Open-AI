"""Tests for RAG circuit breaker (Phase 8)."""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.retrieval.safety.circuit_breaker import (
    bootstrap_rag_circuit_state,
    is_rag_circuit_open_async,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
)
from spark.retrieval.constants import UNAVAILABLE_ANSWER
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.service import RAGService


async def _trip_rag_circuit_async(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    flag = tmp_path / "rag_circuit.flag"
    monkeypatch.setattr(settings, "rag_circuit_flag_path", flag)
    monkeypatch.setattr(settings, "rag_circuit_window_sec", 600)
    monkeypatch.setattr(settings, "rag_circuit_unhandled_fail_threshold", 3)
    await reset_rag_circuit_manual(reason="test_reset")
    for _ in range(3):
        await record_rag_outcome_async("unhandled", enabled=True)


def _trip_rag_circuit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import asyncio

    asyncio.run(_trip_rag_circuit_async(monkeypatch, tmp_path))


@pytest.mark.asyncio
async def test_rag_circuit_trips_on_unhandled_failures(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    await _trip_rag_circuit_async(monkeypatch, tmp_path)
    assert await is_rag_circuit_open_async() is True


@pytest.mark.asyncio
async def test_rag_circuit_manual_reset(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    await _trip_rag_circuit_async(monkeypatch, tmp_path)
    assert await reset_rag_circuit_manual(operator="ops") is True
    assert await is_rag_circuit_open_async() is False


def test_rag_circuit_bootstrap_logs_open_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _trip_rag_circuit(monkeypatch, tmp_path)
    bootstrap_rag_circuit_state()


@pytest.mark.asyncio
async def test_rag_circuit_open_returns_degraded_without_extractive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _trip_rag_circuit_async(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "spark_rag_circuit_enabled", True)

    async def force_open(**_kwargs):
        from spark.retrieval.circuit.types import CircuitDecision, CircuitMode

        return CircuitDecision(mode=CircuitMode.OPEN, skip_llm=True)

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolve_circuit_decision",
        force_open,
    )

    async def _deny_half_open_probe(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolver.allow_half_open_probe",
        _deny_half_open_probe,
    )

    doc = RetrievedDoc(
        page_content="WARNING: Check cooling fan if temperature exceeds 80°C.",
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": str(uuid.uuid4()),
            "source_file": "manual.pdf",
            "document_type": "machine_manual",
            "machine_id": "MC-001",
        },
    )
    svc = RAGService()

    async def fake_resolve(*_args, **_kwargs):
        from spark.retrieval.service import _RetrievalBundle

        return _RetrievalBundle(
            docs=[doc],
            fallback_level=0,
            used_filters={},
            top_doc_score=0.9,
            scope_rf=RAGFilter(machine_id="MC-001"),
        )

    monkeypatch.setattr(svc, "_resolve_retrieval", fake_resolve)

    class ExplodingLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("LLM should not be called when circuit is open")

    monkeypatch.setattr(svc, "_get_llm", lambda: ExplodingLLM())

    result = await svc.query("Servo MC-001 ร้อน", RAGFilter(machine_id="MC-001"))
    assert result.answer == UNAVAILABLE_ANSWER
    assert result.answer_path == "system_degraded"


@pytest.mark.asyncio
async def test_rag_circuit_open_weak_retrieval_returns_no_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await _trip_rag_circuit_async(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "spark_rag_circuit_enabled", True)

    async def force_open(**_kwargs):
        from spark.retrieval.circuit.types import CircuitDecision, CircuitMode

        return CircuitDecision(mode=CircuitMode.OPEN, skip_llm=True)

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolve_circuit_decision",
        force_open,
    )

    async def _deny_half_open_probe(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolver.allow_half_open_probe",
        _deny_half_open_probe,
    )
    svc = RAGService()

    async def fake_resolve(*_args, **_kwargs):
        from spark.retrieval.service import _RetrievalBundle

        return _RetrievalBundle(
            docs=[],
            fallback_level=0,
            used_filters={},
            top_doc_score=0.0,
            scope_rf=RAGFilter(),
        )

    monkeypatch.setattr(svc, "_resolve_retrieval", fake_resolve)
    result = await svc.query("unknown question", RAGFilter())
    # No-data answers are rendered as the helpful no-data message (what was
    # found + how to search better) instead of the terse canned string.
    from spark.retrieval.synthesis import _is_no_data_answer

    assert _is_no_data_answer(result.answer)
    assert result.answer_path == "no_data"
