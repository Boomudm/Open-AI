"""Phase 10 — structured safety uses schema output, not regex JSON extraction."""

from __future__ import annotations

import inspect
import uuid

import pytest

from spark.generation.constrained_safety import run_constrained_safety
from spark.generation.schemas.safety_answer import CitationRef, SafetyAnswerSchema
from spark.generation.types import GenerationInput
from spark.retrieval.models import RetrievedDoc


def test_constrained_safety_has_no_json_block_regex() -> None:
    import spark.generation.constrained_safety as module

    source = inspect.getsource(module)
    assert "_JSON_BLOCK_RE" not in source
    assert "re.search" not in source


@pytest.mark.asyncio
async def test_structured_output_path_used_when_available() -> None:
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="LOTO: 1) Notify supervisor 2) Apply lock and tag.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "document_type": "sop"},
    )
    schema = SafetyAnswerSchema(
        steps=["Notify supervisor", "Apply lock and tag"],
        warnings=["Verify zero energy"],
        citations=[CitationRef(chunk_id=chunk_id)],
        confidence="high",
    )
    structured_called = False

    class StructuredLLM:
        def with_structured_output(self, _schema):
            nonlocal structured_called
            structured_called = True

            class Runnable:
                async def ainvoke(self, _prompt):
                    return schema

            return Runnable()

        async def ainvoke(self, _prompt):
            raise AssertionError("raw JSON fallback must not run when structured output works")

    inp = GenerationInput(
        question="LOTO steps before maintenance",
        docs=[doc],
        llm=StructuredLLM(),
        force_extractive_first=False,
    )
    result = await run_constrained_safety(inp)
    assert structured_called is True
    assert result.citations_verified is True
    assert result.answer_path == "grounded_structured_safety"
