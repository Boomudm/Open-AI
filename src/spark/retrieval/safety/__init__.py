"""Retrieval-time safety policies (Phase 9)."""

from spark.retrieval.safety.admission import rag_admission_guard
from spark.retrieval.safety.circuit_breaker import (
    RAGCircuitDecision,
    RAGCircuitMode,
    get_rag_circuit_status,
    is_rag_circuit_open,
    is_rag_circuit_open_async,
    record_rag_outcome,
    record_rag_outcome_async,
    reset_rag_circuit_manual,
    reset_rag_circuit_manual_blocking,
    resolve_rag_circuit_decision,
)
from spark.retrieval.safety.fallback_ladder import (
    FallbackContext,
    build_fallback_levels,
    run_fallback_ladder,
)
from spark.retrieval.safety.query_policy import QueryPolicyResult, scan_query
from spark.retrieval.safety.rate_limit import (
    check_rag_query_rate_limit,
    rag_inflight_guard,
)
from spark.retrieval.safety.safety_intent import (
    SafetyIntent,
    SafetyIntentKind,
    detect_safety_intent,
    requires_strict_retrieval,
)
from spark.retrieval.safety.scope_guard import filter_machine_conflicts

__all__ = [
    "FallbackContext",
    "QueryPolicyResult",
    "RAGCircuitDecision",
    "RAGCircuitMode",
    "SafetyIntent",
    "SafetyIntentKind",
    "build_fallback_levels",
    "check_rag_query_rate_limit",
    "detect_safety_intent",
    "filter_machine_conflicts",
    "get_rag_circuit_status",
    "is_rag_circuit_open",
    "is_rag_circuit_open_async",
    "rag_inflight_guard",
    "rag_admission_guard",
    "record_rag_outcome",
    "record_rag_outcome_async",
    "requires_strict_retrieval",
    "reset_rag_circuit_manual",
    "reset_rag_circuit_manual_blocking",
    "resolve_rag_circuit_decision",
    "run_fallback_ladder",
    "scan_query",
]
