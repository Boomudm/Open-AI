"""Phase 8 — Prometheus gauge reflects per-factory dependency open state."""

from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.metrics import rag_circuit_open
from spark.retrieval.safety.circuit_breaker import (
    record_rag_outcome_async,
    reset_rag_circuit_manual,
)


@pytest.mark.asyncio
async def test_gauge_set_on_unhandled_trip(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")
    monkeypatch.setattr(settings, "rag_circuit_unhandled_fail_threshold", 3)

    factory_id = "gauge-factory"
    dependency = "unhandled"
    await reset_rag_circuit_manual(factory_id=factory_id, reason="test_reset")
    rag_circuit_open.labels(factory_id=factory_id, dependency=dependency).set(0)

    for _ in range(3):
        await record_rag_outcome_async("unhandled", enabled=True, factory_id=factory_id)

    assert rag_circuit_open.labels(factory_id=factory_id, dependency=dependency)._value.get() == 1.0

    await reset_rag_circuit_manual(factory_id=factory_id, dependency=dependency, reason="test_cleanup")
    assert rag_circuit_open.labels(factory_id=factory_id, dependency=dependency)._value.get() == 0.0
