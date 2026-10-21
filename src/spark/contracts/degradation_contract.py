"""Structured degradation metadata for RAG API responses (remediation v2 Phase 0)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

SystemStatus = Literal[
    "healthy",
    "degraded",
    "critical",
    "unavailable",
]


@dataclass(frozen=True)
class SystemDegradation:
    """Serializable degradation snapshot — wired to API in Phase 10."""

    vector_available: bool
    lexical_available: bool
    rerank_available: bool
    llm_available: bool
    user_message_key: str
    fail_closed: bool
    system_status: SystemStatus = "healthy"
    rerank_degraded: bool = False
    rerank_degraded_policy: str = "ce_active"
    sparse_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def healthy_degradation(*, fail_closed: bool = False) -> SystemDegradation:
    return SystemDegradation(
        vector_available=True,
        lexical_available=True,
        rerank_available=True,
        llm_available=True,
        user_message_key="rag.status.healthy",
        fail_closed=fail_closed,
        system_status="healthy",
    )


def policy_block_degradation(*, fail_closed: bool = True) -> SystemDegradation:
    """Query blocked before retrieval — all legs nominally available, answer refused."""
    return SystemDegradation(
        vector_available=True,
        lexical_available=True,
        rerank_available=True,
        llm_available=True,
        user_message_key="rag.status.query_blocked",
        fail_closed=fail_closed,
        system_status="healthy",
    )


def circuit_open_degradation(*, fail_closed: bool = False) -> SystemDegradation:
    return SystemDegradation(
        vector_available=True,
        lexical_available=True,
        rerank_available=True,
        llm_available=False,
        user_message_key="rag.status.circuit_open",
        fail_closed=fail_closed,
        system_status="degraded",
    )


def from_retrieval_flags(
    *,
    embed_failed: bool = False,
    lexical_failed: bool = False,
    rerank_degraded: bool = False,
    rerank_degraded_policy: str = "ce_active",
    sparse_available: bool = True,
    llm_skipped: bool = False,
    fail_closed: bool = False,
) -> SystemDegradation:
    vector_ok = not embed_failed
    lexical_ok = not lexical_failed
    rerank_ok = not rerank_degraded
    llm_ok = not llm_skipped
    if vector_ok and lexical_ok and rerank_ok and llm_ok and sparse_available:
        return healthy_degradation(fail_closed=fail_closed)
    if not vector_ok and not lexical_ok:
        status: SystemStatus = "unavailable"
        message_key = "rag.status.retrieval_unavailable"
    elif not llm_ok:
        status = "degraded"
        message_key = "rag.status.llm_unavailable"
    else:
        status = "degraded"
        message_key = "rag.status.partial_degradation"
    return SystemDegradation(
        vector_available=vector_ok,
        lexical_available=lexical_ok,
        rerank_available=rerank_ok,
        llm_available=llm_ok,
        user_message_key=message_key,
        fail_closed=fail_closed,
        system_status=status,
        rerank_degraded=rerank_degraded,
        rerank_degraded_policy=rerank_degraded_policy,
        sparse_available=sparse_available,
    )
