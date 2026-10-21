"""Embed/sparse retry policy — transient GPU/OOM/timeout with exponential backoff."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from spark.ingestion.errors import TransientIngestError, classify_exception, transient_ingest_failure
from spark.ingestion.reason_codes import ReasonCode

T = TypeVar("T")

MAX_EMBED_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 0.5


def is_embed_transient(exc: Exception) -> bool:
    """True when the failure is retryable for index-time encode (CUDA/OOM/timeout)."""
    if isinstance(exc, TransientIngestError):
        try:
            code = ReasonCode(exc.reason_code)
        except ValueError:
            return False
        return code in {ReasonCode.EMBED_TRANSIENT, ReasonCode.QDRANT_TIMEOUT}
    classified = classify_exception(exc)
    return classified.transient and classified.code in {
        ReasonCode.EMBED_TRANSIENT,
        ReasonCode.QDRANT_TIMEOUT,
    }


async def with_embed_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = MAX_EMBED_ATTEMPTS,
) -> T:
    """Run an async encode call with jittered exponential backoff on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await factory()
        except Exception as exc:
            last_exc = exc
            if not is_embed_transient(exc) or attempt >= max_attempts - 1:
                if is_embed_transient(exc):
                    raise transient_ingest_failure(
                        ReasonCode.EMBED_TRANSIENT,
                        f"embed exhausted after {max_attempts} attempts: {exc}",
                    ) from exc
                raise
            jitter = random.uniform(0.0, 0.25)
            await asyncio.sleep(_BACKOFF_BASE_SEC * (2**attempt) + jitter)
    raise transient_ingest_failure(
        ReasonCode.EMBED_TRANSIENT,
        f"embed exhausted after {max_attempts} attempts: {last_exc}",
    )
