from uuid import uuid4

import pytest

from spark.schemas.rag import AskResponse
from spark.services.chat_ask_dedupe import get_recent_ask, remember_ask


@pytest.mark.asyncio
async def test_chat_ask_dedupe_returns_cached_response():
    session_id = uuid4()
    response = AskResponse(
        answer="cached",
        sources=[],
        used_filters={},
        cache_hit=True,
        assistant_message_id=uuid4(),
    )
    await remember_ask(session_id, "What is MC-001?", response)
    cached = await get_recent_ask(session_id, "What is MC-001?")
    assert cached is not None
    assert cached.answer == "cached"


@pytest.mark.asyncio
async def test_chat_ask_dedupe_normalizes_whitespace():
    session_id = uuid4()
    response = AskResponse(answer="ok", sources=[], used_filters={}, cache_hit=False)
    await remember_ask(session_id, "  Hello   world ", response)
    cached = await get_recent_ask(session_id, "hello world")
    assert cached is not None
    assert cached.answer == "ok"
