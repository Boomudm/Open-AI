"""Per-factory, per-dependency RAG circuit breakers (Phase 8)."""

from spark.retrieval.circuit.dependency_breaker import (
    bootstrap_rag_circuit_state,
    get_rag_circuit_status,
    is_rag_circuit_open,
    is_rag_circuit_open_async,
    read_admin_flag,
    record_rag_outcome,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
    reset_rag_circuit_manual_blocking,
)
from spark.retrieval.circuit.resolver import resolve_circuit_decision
from spark.retrieval.circuit.types import (
    CircuitDecision,
    CircuitDependency,
    CircuitMode,
    OutcomeKind,
)

# Backward-compatible aliases for Phase 9 callers.
RAGCircuitMode = CircuitMode
RAGCircuitDecision = CircuitDecision


async def resolve_rag_circuit_decision(
    *,
    enabled: bool,
    factory_id: str | None,
) -> CircuitDecision:
    return await resolve_circuit_decision(enabled=enabled, factory_id=factory_id)


async def allow_half_open_probe(factory_id: str | None) -> bool:
    from spark.retrieval.circuit.dependency_breaker import allow_half_open_probe as _probe

    return await _probe(factory_id, CircuitDependency.LLM)


def _read_flag() -> dict | None:
    return read_admin_flag()


__all__ = [
    "CircuitDecision",
    "CircuitDependency",
    "CircuitMode",
    "OutcomeKind",
    "RAGCircuitDecision",
    "RAGCircuitMode",
    "allow_half_open_probe",
    "bootstrap_rag_circuit_state",
    "get_rag_circuit_status",
    "is_rag_circuit_open",
    "is_rag_circuit_open_async",
    "read_admin_flag",
    "record_rag_outcome",
    "record_rag_outcome_async",
    "reset_rag_circuit_manual",
    "reset_rag_circuit_manual_blocking",
    "resolve_circuit_decision",
    "resolve_rag_circuit_decision",
]
