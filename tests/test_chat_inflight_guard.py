"""Unified RAG admission guard tests (Phase 10)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from spark.retrieval.safety.admission import rag_admission_guard


@pytest.mark.asyncio
async def test_rag_admission_guard_composes_rate_limit_and_inflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_rate_limit(**_kwargs) -> None:
        calls.append("rate_limit")

    @asynccontextmanager
    async def fake_inflight(_factory_id):
        calls.append("inflight_enter")
        try:
            yield
        finally:
            calls.append("inflight_exit")

    monkeypatch.setattr(
        "spark.retrieval.safety.admission.check_rag_query_rate_limit",
        fake_rate_limit,
    )
    monkeypatch.setattr(
        "spark.retrieval.safety.admission.rag_inflight_guard",
        fake_inflight,
    )

    async with rag_admission_guard("F-01", user_id="user-1"):
        pass

    assert calls == ["rate_limit", "inflight_enter", "inflight_exit"]
