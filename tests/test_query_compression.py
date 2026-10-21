"""Tests for query compression threshold."""

from __future__ import annotations

import pytest

from spark.services.query_compression import maybe_compress_question


@pytest.mark.asyncio
async def test_short_question_not_compressed() -> None:
    question = "MC-001 ร้อนผิดปกติ"
    result, compressed = await maybe_compress_question(question)
    assert result == question
    assert compressed is None
