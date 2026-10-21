"""Phase 11 — structured safety schema validation."""

from __future__ import annotations

import json
import uuid

import pytest

from spark.generation.citations import validate_structured_safety_citations
from spark.generation.constrained_safety import format_safety_answer, run_constrained_safety
from spark.generation.schemas.safety_answer import CitationRef, SafetyAnswerSchema
from spark.generation.types import GenerationInput
from spark.retrieval.models import RetrievedDoc


def test_safety_answer_schema_requires_confidence_enum() -> None:
    schema = SafetyAnswerSchema.model_validate(
        {
            "steps": ["Notify supervisor"],
            "warnings": ["Do not bypass interlock"],
            "citations": [{"chunk_id": "abc"}],
            "confidence": "high",
        }
    )
    assert schema.confidence == "high"
    rendered = format_safety_answer(schema)
    assert "1. Notify supervisor" in rendered
    assert "คำเตือน:" in rendered


def test_validate_structured_safety_citations_rejects_unknown_chunk() -> None:
    doc = RetrievedDoc(
        page_content="LOTO: isolate energy.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": str(uuid.uuid4())},
    )
    schema = SafetyAnswerSchema(
        steps=["Isolate energy"],
        warnings=[],
        citations=[CitationRef(chunk_id="missing-chunk")],
        confidence="medium",
    )
    ok, cited = validate_structured_safety_citations(schema, [doc])
    assert ok is False
    assert cited == []


@pytest.mark.asyncio
async def test_run_constrained_safety_accepts_valid_json() -> None:
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="LOTO: 1) Notify supervisor 2) Apply lock and tag.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "document_type": "sop"},
    )
    payload = {
        "steps": ["Notify supervisor", "Apply lock and tag"],
        "warnings": ["Verify zero energy"],
        "citations": [{"chunk_id": chunk_id}],
        "confidence": "high",
    }

    class JsonLLM:
        async def ainvoke(self, _prompt: str):
            class Response:
                content = json.dumps(payload, ensure_ascii=False)

            return Response()

    inp = GenerationInput(
        question="LOTO steps before maintenance",
        docs=[doc],
        llm=JsonLLM(),
        force_extractive_first=False,
    )
    result = await run_constrained_safety(inp)
    assert result.citations_verified is True
    assert result.answer_path == "grounded_structured_safety"
    assert chunk_id in result.answer
