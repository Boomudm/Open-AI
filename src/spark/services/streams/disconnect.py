"""Client disconnect handling for SSE generators (app-layer Phase 3 + v2 Phase 5)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Request

from spark.core.logging import get_logger

log = get_logger(__name__)


async def with_sse_keepalive(
    gen: AsyncIterator[str],
    *,
    interval_sec: float = 10.0,
) -> AsyncIterator[str]:
    """Emit SSE comment keepalives while waiting on slow upstream work (RAG/LLM).

    Without these, Next.js/dev proxies can idle-timeout a stream that already sent
    ``connected`` but then spends 20–60s in retrieval before the first token.
    """
    from spark.services.chat_stream import sse_keepalive

    it = gen.__aiter__()
    pending: asyncio.Task[str] | None = asyncio.create_task(it.__anext__())
    try:
        while pending is not None:
            done, _ = await asyncio.wait({pending}, timeout=interval_sec)
            if pending in done:
                try:
                    yield pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.create_task(it.__anext__())
            else:
                yield sse_keepalive()
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        try:
            await gen.aclose()
        except Exception:
            pass


async def track_disconnect(
    request: Request,
    gen: AsyncIterator[str],
    *,
    cancel_event: asyncio.Event | None = None,
    on_disconnect: Callable[[], Awaitable[None]] | None = None,
    poll_interval_sec: float = 0.5,
) -> AsyncIterator[str]:
    """Yield SSE frames and signal cooperative cancellation on stream teardown.

    Starlette's ``StreamingResponse`` already listens for the ASGI disconnect
    message.  Polling ``request.is_disconnected()`` here as well creates a
    second consumer for the request receive channel.  Behind middleware/proxies
    that race can swallow an ``http.response.body`` message and leave the
    browser waiting forever even though the answer was produced.  Let
    StreamingResponse own disconnect detection and use task cancellation to
    propagate it into the RAG/LLM pipeline.
    """
    disconnect = cancel_event if cancel_event is not None else asyncio.Event()
    try:
        async for frame in gen:
            yield frame
    except (asyncio.CancelledError, GeneratorExit):
        disconnect.set()
        raise
    except Exception:
        disconnect.set()
        raise
    finally:
        disconnect.set()
        try:
            await gen.aclose()
        except Exception:
            pass
        log.info("stream_closed", path=request.url.path)
        if on_disconnect is not None:
            try:
                await on_disconnect()
            except Exception as exc:
                log.warning("stream_disconnect_cleanup_failed", error=str(exc)[:200])
