"""Stream path respects open RAG circuit — no LLM invoke (Phase 9)."""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.retrieval.constants import UNAVAILABLE_ANSWER
from spark.retrieval.kernel import RAGKernelInput
from spark.retrieval.safety.circuit_breaker import record_rag_outcome_async, reset_rag_circuit_manual
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.service import RAGService


@pytest.mark.asyncio
async def test_stream_circuit_open_skips_llm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")
    monkeypatch.setattr(settings, "rag_circuit_unhandled_fail_threshold", 1)
    monkeypatch.setattr(settings, "spark_rag_circuit_enabled", True)

    await reset_rag_circuit_manual(reason="test_reset")
    await record_rag_outcome_async("unhandled", enabled=True)

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
            raise RuntimeError("LLM must not be called when circuit is open")

    monkeypatch.setattr(svc, "_get_llm", lambda: ExplodingLLM())

    inp = RAGKernelInput(
        question="Servo MC-001 ร้อน",
        rf=RAGFilter(machine_id="MC-001"),
        stream=True,
        skip_llm=True,
        circuit_enabled=True,
        circuit_mode="open",
    )
    chunks: list[str | object] = []
    async for item in svc.execute_stream(inp):
        chunks.append(item)

    assert any(isinstance(item, str) and item for item in chunks)
    final = chunks[-1]
    assert getattr(final, "answer_path", None) == "system_degraded"
    assert getattr(final, "answer", "") == UNAVAILABLE_ANSWER
