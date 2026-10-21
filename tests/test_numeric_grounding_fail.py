"""Phase 11 — numeric grounding failure answer_path."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.generation.citations import citation_validation_failure, validate_grounded_citations
from spark.generation.types import GenerationInput
from spark.retrieval.constants import NO_DATA_ANSWER
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
        },
    )


def test_citation_validation_failure_detects_numeric_hallucination() -> None:
    doc = _doc("Maximum torque 25 Nm.")
    cid = doc.payload["chunk_id"]
    answer = f"Use torque 30 Nm [chunk_id:{cid}]"
    ok, _ = validate_grounded_citations(answer, [doc])
    assert ok is False
    assert citation_validation_failure(answer, [doc]) == "numeric_grounding_fail"


class FakeLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def ainvoke(self, _payload):
        class Response:
            pass

        resp = Response()
        resp.content = self._answer
        return resp


@pytest.mark.asyncio
async def test_grounded_llm_returns_numeric_grounding_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _doc("Maximum torque 25 Nm.")
    cid = doc.payload["chunk_id"]
    monkeypatch.setattr(
        "spark.generation.extractive.format_extractive_answer",
        AsyncMock(return_value=None),
    )
    inp = GenerationInput(
        question="แรงบิดสูงสุดเท่าไร",
        docs=[doc],
        llm=FakeLLM(f"ใช้แรงบิด 30 Nm [chunk_id:{cid}]"),
        force_extractive_first=False,
    )
    from spark.generation import grounded_llm

    result = await grounded_llm.run_grounded_llm(inp)
    assert result.answer == NO_DATA_ANSWER
    assert result.answer_path == "numeric_grounding_fail"
