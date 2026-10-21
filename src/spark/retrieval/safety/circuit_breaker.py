"""Distributed RAG circuit breaker — re-exports Phase 8 per-factory bulkhead module."""

from __future__ import annotations

from spark.retrieval.circuit import (
    CircuitDecision,
    CircuitDependency,
    CircuitMode,
    OutcomeKind,
    RAGCircuitDecision,
    RAGCircuitMode,
    allow_half_open_probe,
    bootstrap_rag_circuit_state,
    get_rag_circuit_status,
    is_rag_circuit_open,
    is_rag_circuit_open_async,
    record_rag_outcome,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
    reset_rag_circuit_manual_blocking,
    resolve_circuit_decision,
    resolve_rag_circuit_decision,
)
from spark.retrieval.circuit.dependency_breaker import read_admin_flag as _read_flag

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
    "record_rag_outcome",
    "record_rag_outcome_async",
    "reset_rag_circuit_manual",
    "reset_rag_circuit_manual_blocking",
    "resolve_circuit_decision",
    "resolve_rag_circuit_decision",
    "_read_flag",
]
