"""Non-blocking storage byte streaming for async FastAPI handlers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator


def _next_chunk(sync_iter: Iterator[bytes]) -> bytes | None:
    try:
        return next(sync_iter)
    except StopIteration:
        return None


async def iter_sync_bytes(sync_iter: Iterator[bytes]) -> AsyncIterator[bytes]:
    """Yield chunks from a blocking iterator without blocking the event loop."""
    while True:
        chunk = await asyncio.to_thread(_next_chunk, sync_iter)
        if chunk is None:
            break
        yield chunk
