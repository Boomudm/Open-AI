"""Phase 11 — real token streaming yields multiple deltas before RAGResult."""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

import pytest

from spark.generation.pipeline import build_generation_input
from spark.generation.streaming import stream_grounded_answer
from spark.retrieval.models import RAGFilter, RAGStreamToken, RetrievedDoc
from spark.retrieval.service import RAGService, _RetrievalBundle


class StreamingFakeLLM:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.ainvoke_calls = 0

    async def astream(self, _payload: Any) -> AsyncIterator[Any]:
        for piece in self._chunks:

            class Chunk:
                content = piece

            yield Chunk()

    async def ainvoke(self, _payload: Any) -> Any:
        self.ainvoke_calls += 1

        class Response:
            content = "".join(self._chunks)

        return Response()


class UsageStreamingFakeLLM(StreamingFakeLLM):
    async def astream(self, _payload: Any) -> AsyncIterator[Any]:
        for piece in self._chunks:

            class Chunk:
                content = piece
                usage_metadata = None

            yield Chunk()

        class UsageChunk:
            content = ""
            usage_metadata = {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
            }

        yield UsageChunk()


@pytest.mark.asyncio
async def test_stream_grounded_answer_emits_multiple_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
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
    llm = StreamingFakeLLM(["Pressure ", "limit ", f"5 bar [chunk_id:{chunk_id}]"])

    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=llm,
        extractive_first=False,
    )

    tokens: list[str] = []
    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind in {"token", "token_provisional"}:
            tokens.append(event.delta)
        elif event.kind == "done":
            final = event.result

    assert len(tokens) >= 2
    assert final is not None
    assert final.citations_verified is True
    assert llm.ainvoke_calls == 0


@pytest.mark.asyncio
async def test_stream_grounded_answer_attaches_provider_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
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
    llm = UsageStreamingFakeLLM(["Pressure ", f"5 bar [chunk_id:{chunk_id}]"])
    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=llm,
        extractive_first=False,
    )

    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind == "done":
            final = event.result

    assert final is not None
    assert final.llm_usage is not None
    assert final.llm_usage["prompt_tokens"] == 11
    assert final.llm_usage["completion_tokens"] == 7
    assert final.llm_usage["total_tokens"] == 18


@pytest.mark.asyncio
async def test_always_live_streams_numeric_question_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
    monkeypatch.setattr(settings, "spark_stream_always_live", True)
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
    llm = StreamingFakeLLM(["Pressure ", "limit ", f"5 bar [chunk_id:{chunk_id}]"])

    inp = build_generation_input(
        question="What is the 5 bar pressure limit?",
        docs=[doc],
        llm=llm,
        extractive_first=False,
    )

    tokens: list[str] = []
    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind in {"token", "token_provisional"}:
            tokens.append(event.delta)
        elif event.kind == "done":
            final = event.result

    assert len(tokens) >= 2
    assert final is not None
    assert final.citations_verified is True
    assert llm.ainvoke_calls == 0


@pytest.mark.asyncio
async def test_query_stream_impl_yields_tokens_before_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
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
    svc = RAGService()
    llm = StreamingFakeLLM(["Pressure ", f"5 bar [chunk_id:{chunk_id}]"])

    async def fake_resolve(*_args, **_kwargs):
        return _RetrievalBundle(
            docs=[doc],
            fallback_level=0,
            used_filters={},
            top_doc_score=0.9,
            scope_rf=RAGFilter(factory_id="F-01"),
        )

    monkeypatch.setattr(svc, "_resolve_retrieval", fake_resolve)
    monkeypatch.setattr(svc, "_get_llm", lambda: llm)

    from spark.generation.policy import GenerationPolicy

    async def _fake_policy(rf):
        return GenerationPolicy(
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
        )

    monkeypatch.setattr(
        "spark.retrieval.service.resolve_generation_policy",
        _fake_policy,
    )

    items: list[str | object] = []
    async for item in svc._query_stream_impl(
        "pressure limit?",
        RAGFilter(factory_id="F-01"),
        top_k=4,
        _start=0.0,
        allowed_doc_ids=None,
    ):
        items.append(item)

    token_items = [item for item in items if isinstance(item, RAGStreamToken)]
    assert len(token_items) >= 2
    assert items[-1].answer_path == "grounded_llm"
    from spark.retrieval.models import RAGStreamPhaseMeta

    phase_metas = [item for item in items if isinstance(item, RAGStreamPhaseMeta)]
    # First phase event fires before retrieval so the client can show progress
    # immediately; it carries no degradation info yet.
    assert phase_metas[0].retrieval_report == {"phase": "searching"}
    post_retrieval = next(m for m in phase_metas if m.system_degradation is not None)
    assert items.index(post_retrieval) < items.index(token_items[0])


@pytest.mark.asyncio
async def test_suppressed_answer_supersedes_streamed_provisional_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected answer must be retracted from the client, not just from storage.

    The web client renders provisional deltas as they arrive and only swaps them
    out on a citation_block frame. A suppression that ends on a bare `done`
    therefore leaves the rejected text on screen while the stored message says
    no-data — here, a fabricated pressure limit the backend already refused.
    """
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
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
    # Cites a real chunk but states a number that contradicts it.
    fabrication = f"The operating pressure limit is 9 bar [chunk_id:{chunk_id}]"
    llm = StreamingFakeLLM([fabrication[:18], fabrication[18:]])

    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=llm,
        extractive_first=False,
    )

    streamed: list[str] = []
    superseding_text: str | None = None
    final = None
    async for event in stream_grounded_answer(inp):
        if event.kind in {"token", "token_provisional"}:
            streamed.append(event.delta)
        elif event.kind == "citation_block":
            superseding_text = event.result.answer if event.result else ""
        elif event.kind == "done":
            final = event.result

    assert final is not None
    assert final.answer_path == "numeric_grounding_fail"
    assert "9 bar" in "".join(streamed), "precondition: fabrication reached the client"
    assert superseding_text is not None, (
        "suppressed answer sent no citation_block — the fabricated number stays "
        "on the user's screen while storage says no-data"
    )
    assert superseding_text == final.answer
    assert "9 bar" not in superseding_text
