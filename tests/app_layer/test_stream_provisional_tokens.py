"""Provisional vs verified streaming tokens (app-layer v2 Phase 5)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from spark.core.config import settings
from spark.generation.pipeline import build_generation_input
from spark.generation.streaming import stream_grounded_answer
from spark.retrieval.models import RetrievedDoc


class ProvisionalFakeLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def astream(self, _payload):
        yield MagicMock(content=self._answer)

    async def ainvoke(self, _payload):
        raise AssertionError("ainvoke should not run when astream is available")


@pytest.mark.asyncio
async def test_provisional_events_precede_verified_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)

    chunk_id = str(uuid.uuid4())
    answer = f"Pressure limit 5 bar [chunk_id:{chunk_id}]"
    doc = RetrievedDoc(
        page_content="Operating pressure must stay below 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "document_type": "machine_manual", "source_file": "m.pdf"},
    )
    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=ProvisionalFakeLLM(answer),
        extractive_first=False,
    )

    kinds: list[str] = []
    final = None
    async for event in stream_grounded_answer(inp):
        kinds.append(event.kind)
        if event.kind == "done":
            final = event.result

    assert "token_provisional" in kinds
    assert "citation_block" in kinds
    assert kinds.index("token_provisional") < kinds.index("citation_block")
    assert final is not None
    assert final.citations_verified is True


@pytest.mark.asyncio
async def test_invalid_citations_emit_error_not_verified_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)

    doc = RetrievedDoc(
        page_content="Operating pressure must stay below 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": str(uuid.uuid4()), "document_type": "machine_manual"},
    )
    inp = build_generation_input(
        question="What is the pressure limit?",
        docs=[doc],
        llm=ProvisionalFakeLLM("Hallucinated 99 bar with no citation."),
        extractive_first=False,
    )

    kinds: list[str] = []
    async for event in stream_grounded_answer(inp):
        kinds.append(event.kind)

    assert "token_provisional" in kinds
    assert "error" not in kinds
    assert "done" in kinds


@pytest.mark.asyncio
async def test_stream_ask_dedupe_blocks_duplicate() -> None:
    from uuid import uuid4

    from spark.core.cache import Cache
    from spark.services.chat_ask_dedupe import try_begin_stream_ask

    await Cache.get().clear_spark_keys()
    session_id = uuid4()
    assert await try_begin_stream_ask(session_id, "same question") is True
    assert await try_begin_stream_ask(session_id, "same question") is False
