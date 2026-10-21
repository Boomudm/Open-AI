from __future__ import annotations

import pytest

from spark.services.session_title_service import (
    generate_session_title,
    is_default_title,
    needs_llm_title,
)


def test_is_default_title() -> None:
    assert is_default_title(None) is True
    assert is_default_title("New chat") is True
    assert is_default_title("แชทใหม่") is True
    assert is_default_title("สายพานรั่ว") is False


def test_needs_llm_title_long_question() -> None:
    long_q = "a" * 90
    assert needs_llm_title(long_q, "short") is True


def test_needs_llm_title_short_question() -> None:
    assert needs_llm_title("สายพานรั่วไหม", "สายพานรั่วไหม") is False


@pytest.mark.asyncio
async def test_generate_session_title_heuristic(monkeypatch) -> None:
    async def _fail(*_a, **_k):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr(
        "spark.services.session_title_service._llm_title",
        _fail,
    )
    title = await generate_session_title("สายพานรั่วไหม", machine_id="MC-001")
    assert title.startswith("MC-001 · ")
    assert "สายพาน" in title
