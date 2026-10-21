"""Chaos — factory circuit isolation under concurrent load."""

from __future__ import annotations

import asyncio

import pytest

from spark.core.config import settings
from spark.retrieval.circuit.dependency_breaker import is_dependency_open
from spark.retrieval.circuit.types import CircuitDependency
from spark.retrieval.safety.circuit_breaker import (
    is_rag_circuit_open_async,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
)


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_hundred_concurrent_checks_do_not_trip_unrelated_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")
    monkeypatch.setattr(settings, "rag_circuit_unhandled_fail_threshold", 3)

    await reset_rag_circuit_manual(reason="chaos_reset")
    for _ in range(3):
        await record_rag_outcome_async("unhandled", enabled=True, factory_id="factory-a")

    async def _probe_factory_b() -> bool:
        return await is_rag_circuit_open_async("factory-b")

    results = await asyncio.gather(*[_probe_factory_b() for _ in range(100)])
    assert all(result is False for result in results)
    assert await is_dependency_open("factory-a", CircuitDependency.UNHANDLED)
    assert not await is_dependency_open("factory-b", CircuitDependency.UNHANDLED)
