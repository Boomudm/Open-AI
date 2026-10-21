"""Phase 10 — validated pseudo-stream emits tokens only after grounding."""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.core.metrics import generation_stream_pseudo_total
from spark.generation.pipeline import build_generation_input
from spark.generation.streaming import stream_grounded_answer


class StreamingFakeLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.astream_calls = 0
        self.ainvoke_calls = 0

    async def astream(self, _payload):
        self.astream_calls += 1
        raise AssertionError("live token stream must not run in default pseudo-stream mode")

    async def ainvoke(self, _payload):
        self.ainvoke_calls += 1

        class Response:
            content = self._answer

        return Response()


@pytest.mark.asyncio
async def test_pseudo_stream_emits_validated_chunks_without_live_astream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "spark_stream_live_tokens", False)
    assert settings.effective_spark_stream_live_tokens is False
    chunk_id = str(uuid.uuid4())
    answer = f"Pressure limit 5 bar [chunk_id:{chunk_id}]"
    llm = StreamingFakeLLM(answer)

    from spark.retrieval.models import RetrievedDoc

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
    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=llm,
        extractive_first=False,
    )

    before = generation_stream_pseudo_total._value.get()  # type: ignore[attr-defined]
    tokens: list[str] = []
    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind == "token":
            tokens.append(event.delta)
        elif event.kind == "done":
            final = event.result

    after = generation_stream_pseudo_total._value.get()  # type: ignore[attr-defined]
    assert after >= before + 1
    assert llm.astream_calls == 0
    assert llm.ainvoke_calls >= 1
    assert len(tokens) >= 1
    assert final is not None
    assert final.citations_verified is True
    assert "".join(tokens) == final.answer
