"""Production profile extractive flags no longer bypass grounded LLM."""

from __future__ import annotations

import uuid

import pytest

from spark.generation.pipeline import build_generation_input, generate
from spark.generation.policy import GenerationPolicy
from spark.retrieval.models import RetrievedDoc


def _doc(text: str) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": str(uuid.uuid4()),
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
        },
    )


@pytest.mark.asyncio
async def test_test_profile_allows_llm_for_non_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Operating pressure must stay below 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
        },
    )
    policy = GenerationPolicy(
        extractive_first_for_safety_types=False,
        extractive_first_for_procedure=False,
    )
    llm_called = False

    class GroundedLLM:
        async def ainvoke(self, _payload):
            nonlocal llm_called
            llm_called = True

            class Response:
                content = f"Pressure limit 5 bar [chunk_id:{chunk_id}]"

            return Response()

    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=GroundedLLM(),
        policy=policy,
    )
    assert inp.intent_requires_extractive() is False

    out = await generate(inp)
    assert llm_called is True
    assert out.result.answer_path == "grounded_llm"


@pytest.mark.asyncio
async def test_production_policy_flags_do_not_skip_grounded_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_id = str(uuid.uuid4())
    doc = _doc("Step 1: Open guard. Step 2: Inspect belt tension. Step 3: Close guard.")
    doc.payload["chunk_id"] = chunk_id
    policy = GenerationPolicy(
        extractive_first_for_safety_types=True,
        extractive_first_for_procedure=True,
    )
    monkeypatch.setattr(
        "spark.generation.pipeline.apply_nli_gate",
        lambda _question, result, **kwargs: result,
    )

    class GroundedLLM:
        called = False

        async def ainvoke(self, *_args, **_kwargs):
            self.called = True

            class Response:
                content = f"Open guard, inspect belt tension, then close guard [chunk_id:{chunk_id}]"

            return Response()

    llm = GroundedLLM()
    inp = build_generation_input(
        question="What are the steps to inspect the belt on MC-001?",
        docs=[doc],
        llm=llm,
        policy=policy,
    )
    assert inp.intent_requires_extractive() is False
    out = await generate(inp)
    assert llm.called is True
    assert out.result.generation_mode == "grounded_llm"
    assert out.result.citations_verified is True
