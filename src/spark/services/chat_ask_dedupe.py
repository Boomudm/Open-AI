"""Short-window dedupe for identical chat ask requests (Redis-backed)."""

from __future__ import annotations

import hashlib
from uuid import UUID

from spark.core.cache import Cache
from spark.schemas.rag import AskResponse

_DEDUPE_WINDOW_SEC = 2
_STREAM_DEDUPE_WINDOW_SEC = 3
_KEY_PREFIX = "spark:chat:dedupe:"
_STREAM_KEY_PREFIX = "spark:chat:ask:dedupe:"


def _question_hash(session_id: UUID, question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha256(f"{session_id}:{normalized}".encode()).hexdigest()


def _cache_key(session_id: UUID, question: str) -> str:
    return f"{_KEY_PREFIX}{_question_hash(session_id, question)}"


async def get_recent_ask(session_id: UUID, question: str) -> AskResponse | None:
    cache = Cache.get()
    raw = await cache.get_json(_cache_key(session_id, question))
    if not isinstance(raw, dict):
        return None
    try:
        return AskResponse.model_validate(raw)
    except Exception:
        return None


async def remember_ask(session_id: UUID, question: str, response: AskResponse) -> None:
    cache = Cache.get()
    await cache.set_json(
        _cache_key(session_id, question),
        response.model_dump(mode="json"),
        ttl=_DEDUPE_WINDOW_SEC,
    )


def _stream_cache_key(session_id: UUID, question: str) -> str:
    return f"{_STREAM_KEY_PREFIX}{_question_hash(session_id, question)}"


async def try_begin_stream_ask(session_id: UUID, question: str) -> bool:
    """Claim a short-lived stream dedupe slot (returns False when duplicate in-flight)."""
    cache = Cache.get()
    key = _stream_cache_key(session_id, question)
    existing = await cache.get_json(key)
    if isinstance(existing, dict) and existing.get("inflight"):
        return False
    await cache.set_json(key, {"inflight": True}, ttl=_STREAM_DEDUPE_WINDOW_SEC)
    return True


async def finish_stream_ask(
    session_id: UUID,
    question: str,
    response: AskResponse | None = None,
) -> None:
    """Release stream dedupe slot; optionally remember completed response."""
    cache = Cache.get()
    key = _stream_cache_key(session_id, question)
    if response is not None:
        await remember_ask(session_id, question, response)
    await cache.delete(key)
