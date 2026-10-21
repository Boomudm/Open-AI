"""SSE client disconnect releases RAG inflight slot (app-layer Phase 3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from starlette.requests import Request

from spark.services.streams.disconnect import track_disconnect


def _request() -> Request:
  return Request(
    {
      "type": "http",
      "method": "POST",
      "path": "/api/v1/chat/sess/ask",
      "raw_path": b"/api/v1/chat/sess/ask",
      "root_path": "",
      "scheme": "http",
      "query_string": b"",
      "headers": [],
      "client": ("testclient", 50000),
      "server": ("testserver", 80),
    }
  )


@pytest.mark.asyncio
async def test_disconnect_invokes_cleanup_callback(monkeypatch: pytest.MonkeyPatch) -> None:
  cleaned = asyncio.Event()

  async def _on_disconnect() -> None:
    cleaned.set()

  async def _slow_gen() -> AsyncIterator[str]:
    for i in range(10):
      yield f"data: {i}\n\n"
      await asyncio.sleep(0.1)

  request = _request()
  disconnect_calls = 0

  async def _is_disconnected() -> bool:
    nonlocal disconnect_calls
    disconnect_calls += 1
    return disconnect_calls >= 2

  monkeypatch.setattr(request, "is_disconnected", _is_disconnected)

  frames = []
  async for frame in track_disconnect(request, _slow_gen(), on_disconnect=_on_disconnect):
    frames.append(frame)

  assert cleaned.is_set()
  assert len(frames) < 10


@pytest.mark.asyncio
async def test_rag_inflight_guard_releases_on_generator_close() -> None:
    from spark.retrieval.safety.admission import rag_admission_guard
    from spark.retrieval.safety.rate_limit import release_rag_inflight_slot

    factory_id = "F-TEST"
    await release_rag_inflight_slot(factory_id)

    async def _rag_stream() -> AsyncIterator[str]:
        async with rag_admission_guard(factory_id):
            yield "token"
            await asyncio.sleep(0.05)

    gen = _rag_stream()
    await gen.__anext__()
    await gen.aclose()

    await release_rag_inflight_slot(factory_id)
