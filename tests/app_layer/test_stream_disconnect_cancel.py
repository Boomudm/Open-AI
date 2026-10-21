"""Disconnect cancels in-flight RAG stream work (app-layer v2 Phase 5)."""

from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from spark.generation.pipeline import build_generation_input
from spark.generation.streaming import stream_grounded_answer
from spark.retrieval.models import RetrievedDoc
from spark.services.streams.disconnect import track_disconnect


class SlowStreamingLLM:
    def __init__(self) -> None:
        self.cancel_observed = False

    async def astream(self, _payload):
        for idx in range(20):
            await asyncio.sleep(0.05)
            yield MagicMock(content=f"chunk-{idx} ")


async def _slow_stream(cancel_event: asyncio.Event):
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Spec value 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "document_type": "manual"},
    )
    inp = build_generation_input(
        question="pressure?",
        docs=[doc],
        llm=SlowStreamingLLM(),
        extractive_first=False,
    )
    inp.cancel_event = cancel_event
    async for _event in stream_grounded_answer(inp):
        if cancel_event.is_set():
            return


@pytest.mark.asyncio
async def test_disconnect_sets_cancel_within_one_second() -> None:
    cancel_event = asyncio.Event()
    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/chat/test/ask"
    disconnect = asyncio.Event()

    async def _is_disconnected() -> bool:
        return disconnect.is_set()

    request.is_disconnected = AsyncMock(side_effect=_is_disconnected)

    async def _producer() -> asyncio.AsyncIterator[str]:
        task = asyncio.create_task(_slow_stream(cancel_event))
        try:
            while not task.done():
                if cancel_event.is_set():
                    break
                await asyncio.sleep(0.05)
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, TimeoutError):
            task.cancel()
        yield "event: token\ndata: {}\n\n"

    started = time.monotonic()
    disconnect.set()
    async for _frame in track_disconnect(request, _producer(), cancel_event=cancel_event):
        pass
    elapsed = time.monotonic() - started
    assert cancel_event.is_set()
    assert elapsed < 1.0
