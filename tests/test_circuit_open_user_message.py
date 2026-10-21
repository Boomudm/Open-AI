"""Circuit-open UX returns system_degraded when retrieval exists (Phase 10)."""

from __future__ import annotations

import uuid

import pytest

from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.service import RAGService, _RetrievalBundle, _generate_under_circuit_open


@pytest.mark.asyncio
async def test_circuit_open_empty_retrieval_returns_no_data() -> None:
    gen = await _generate_under_circuit_open("question", [])
    assert gen.answer == NO_DATA_ANSWER
    assert gen.answer_path == "no_data"


@pytest.mark.asyncio
async def test_circuit_open_with_retrieval_returns_system_degraded() -> None:
    doc = RetrievedDoc(
        page_content="unrelated blob",
        score=0.2,
        vector_score=0.2,
        payload={"chunk_id": str(uuid.uuid4())},
    )
    gen = await _generate_under_circuit_open("question", [doc])
    assert gen.answer == UNAVAILABLE_ANSWER
    assert gen.answer_path == "system_degraded"


@pytest.mark.asyncio
async def test_query_skip_llm_attaches_circuit_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = RAGService()

    async def fake_resolve(*_args, **_kwargs):
        doc = RetrievedDoc(
            page_content="blob",
            score=0.2,
            vector_score=0.2,
            payload={"chunk_id": str(uuid.uuid4())},
        )
        return _RetrievalBundle(
            docs=[doc],
            fallback_level=0,
            used_filters={},
            top_doc_score=0.2,
            scope_rf=RAGFilter(factory_id="F-01"),
        )

    monkeypatch.setattr(svc, "_resolve_retrieval", fake_resolve)

    async def force_open(**_kwargs):
        from spark.retrieval.circuit.types import CircuitDecision, CircuitMode

        return CircuitDecision(mode=CircuitMode.OPEN, skip_llm=True)

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolve_circuit_decision",
        force_open,
    )

    result = await svc.query("question", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "system_degraded"
    assert result.system_degradation is not None
    assert result.system_degradation.get("user_message_key") == "rag.status.circuit_open"
