"""Phase 8 — dependency bulkheads trip independently."""

from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.retrieval.circuit import resolve_circuit_decision
from spark.retrieval.circuit.dependency_breaker import is_dependency_open
from spark.retrieval.circuit.types import CircuitDependency
from spark.retrieval.safety.circuit_breaker import (
    record_rag_outcome_async,
    reset_rag_circuit_manual,
)


@pytest.mark.asyncio
async def test_embed_trip_does_not_skip_llm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")

    async def _deny_probe(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolver.allow_half_open_probe",
        _deny_probe,
    )

    await reset_rag_circuit_manual(factory_id="f-dep", reason="test_reset")
    for _ in range(10):
        await record_rag_outcome_async("embed_error", enabled=True, factory_id="f-dep")

    assert await is_dependency_open("f-dep", CircuitDependency.EMBED)
    assert not await is_dependency_open("f-dep", CircuitDependency.LLM)

    decision = await resolve_circuit_decision(enabled=True, factory_id="f-dep")
    assert decision.skip_llm is False
    assert decision.embed_breaker_open is True
    assert decision.force_rerank_degraded is False


@pytest.mark.asyncio
async def test_rerank_trip_forces_degraded_not_llm_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "rag_circuit_flag_path", tmp_path / "rag_circuit.flag")
    monkeypatch.setattr(settings, "rag_circuit_rerank_gate_fail_rate_threshold", 0.25)

    async def _deny_probe(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        "spark.retrieval.circuit.resolver.allow_half_open_probe",
        _deny_probe,
    )

    await reset_rag_circuit_manual(factory_id="f-rerank", reason="test_reset")
    for _ in range(10):
        await record_rag_outcome_async("rerank_gate_fail", enabled=True, factory_id="f-rerank")

    assert await is_dependency_open("f-rerank", CircuitDependency.RERANK)
    assert not await is_dependency_open("f-rerank", CircuitDependency.LLM)

    decision = await resolve_circuit_decision(enabled=True, factory_id="f-rerank")
    assert decision.skip_llm is False
    assert decision.force_rerank_degraded is True
