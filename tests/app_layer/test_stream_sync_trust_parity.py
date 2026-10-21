"""Phase 5 — stream/sync generation parity with live tokens enabled."""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.generation.pipeline import build_generation_input, generate
from spark.generation.policy import GenerationPolicy
from spark.generation.streaming import stream_grounded_answer
from spark.retrieval.models import RetrievedDoc


@pytest.mark.asyncio
async def test_stream_and_sync_trust_parity_with_live_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
    assert settings.effective_spark_stream_live_tokens is True

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
        extractive_first_for_safety_types=True,
        extractive_first_for_procedure=True,
    )
    monkeypatch.setattr(
        "spark.generation.pipeline.apply_nli_gate",
        lambda _question, result, **kwargs: result,
    )

    class GroundedLLM:
        async def ainvoke(self, *_args, **_kwargs):
            class Response:
                content = f"Pressure limit 5 bar [chunk_id:{chunk_id}]"

            return Response()

    question = "What is the pressure limit?"
    llm = GroundedLLM()
    inp = build_generation_input(
        question=question,
        docs=[doc],
        llm=llm,
        policy=policy,
    )

    sync_out = await generate(inp)
    stream_result = None
    async for event in stream_grounded_answer(inp):
        if event.kind == "done" and event.result is not None:
            stream_result = event.result

    assert stream_result is not None
    assert stream_result.answer_path == sync_out.result.answer_path
    assert stream_result.generation_mode == sync_out.result.generation_mode
    assert stream_result.citations_verified == sync_out.result.citations_verified


def test_production_profile_defaults_live_tokens() -> None:
    from spark.core.app_profile import AppProfile

    prod = AppProfile.for_env(app_env="production", spark_profile="production")
    assert prod.live_token_stream_default is True
