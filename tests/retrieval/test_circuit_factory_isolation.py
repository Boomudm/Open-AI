"""Phase 8 — factory-scoped circuit breakers do not cross tenants."""

from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.retrieval.circuit.dependency_breaker import is_dependency_open
from spark.retrieval.circuit.types import CircuitDependency
from spark.retrieval.safety.circuit_breaker import (
    is_rag_circuit_open_async,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
)


@pytest.mark.asyncio
async def test_factory_a_trip_does_not_open_factory_b(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")
    monkeypatch.setattr(settings, "rag_circuit_unhandled_fail_threshold", 3)

    await reset_rag_circuit_manual(reason="test_reset")
    for _ in range(3):
        await record_rag_outcome_async("unhandled", enabled=True, factory_id="factory-a")

    assert await is_dependency_open("factory-a", CircuitDependency.UNHANDLED)
    assert not await is_dependency_open("factory-b", CircuitDependency.UNHANDLED)
    assert await is_rag_circuit_open_async("factory-a") is True
    assert await is_rag_circuit_open_async("factory-b") is False
