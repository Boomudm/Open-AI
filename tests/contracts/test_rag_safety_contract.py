"""Contract: Phase 8 RAG safety and circuit breakers."""

from __future__ import annotations


def test_rag_circuit_and_fallback_exports() -> None:
    from spark.retrieval.safety.circuit_breaker import is_rag_circuit_open, reset_rag_circuit_manual
    from spark.retrieval.safety.fallback_ladder import run_fallback_ladder
    from spark.retrieval.safety.rate_limit import check_rag_query_rate_limit

    assert callable(is_rag_circuit_open)
    assert callable(reset_rag_circuit_manual)
    assert callable(run_fallback_ladder)
    assert callable(check_rag_query_rate_limit)


def test_ask_request_supports_scope_broadening_flag() -> None:
    from spark.schemas.rag import AskRequest

    req = AskRequest(question="test question", allow_scope_broadening=True)
    assert req.allow_scope_broadening is True
