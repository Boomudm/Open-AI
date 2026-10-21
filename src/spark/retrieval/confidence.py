"""Confidence tier derivation from authoritative RAG answer signals (Phase 12)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ConfidenceTier = Literal["high", "medium", "low"]

_LOW_ANSWER_PATHS = frozenset(
    {
        "no_data",
        "llm_unavailable",
        "numeric_grounding_fail",
        "nli_gate_fail",
        "query_policy_block",
        "embed_circuit_open",
        "service_unavailable",
        "rag_circuit_open",
        "system_degraded",
    }
)


@dataclass(frozen=True)
class ConfidenceSignals:
    top_doc_score: float
    source_count: int
    fallback_level: int
    route: str
    answer_path: str = "unknown"
    citations_verified: bool = False
    rerank_degraded_policy: str | None = None
    system_degradation: dict[str, Any] | None = None

    @property
    def tier(self) -> ConfidenceTier:
        if self.route == "sql":
            return "high" if self.fallback_level == 0 else "medium"

        if not self.citations_verified:
            return "low"
        if self.answer_path in _LOW_ANSWER_PATHS:
            return "low"

        degradation = self.system_degradation or {}
        if degradation.get("fail_closed"):
            return "low"

        policy = (self.rerank_degraded_policy or "ce_active").lower()
        if policy != "ce_active":
            if self.fallback_level >= 2 or self.source_count == 0:
                return "low"
            if self.top_doc_score >= 0.5 and self.source_count >= 1:
                return "medium"
            return "low"

        if self.fallback_level >= 2:
            return "low"
        if self.source_count == 0:
            return "low"
        if self.fallback_level == 0 and self.top_doc_score >= 0.55 and self.source_count >= 1:
            return "high"
        return "medium"


def confidence_from_rag(
    *,
    top_doc_score: float,
    source_count: int,
    fallback_level: int,
    answer_path: str = "grounded_llm",
    citations_verified: bool = False,
    rerank_degraded_policy: str | None = None,
    system_degradation: dict[str, Any] | None = None,
) -> ConfidenceSignals:
    return ConfidenceSignals(
        top_doc_score=top_doc_score,
        source_count=source_count,
        fallback_level=fallback_level,
        route="rag",
        answer_path=answer_path,
        citations_verified=citations_verified,
        rerank_degraded_policy=rerank_degraded_policy,
        system_degradation=system_degradation,
    )


def confidence_from_sql(
    *,
    reason_code: str | None,
    row_count: int | None,
    fallback_level: int = 0,
    answer_path: str = "sql",
) -> ConfidenceSignals:
    ok = reason_code == "ok" and (row_count or 0) >= 0
    return ConfidenceSignals(
        top_doc_score=1.0 if ok else 0.0,
        source_count=1 if ok and (row_count or 0) > 0 else 0,
        fallback_level=fallback_level if ok else max(fallback_level, 2),
        route="sql",
        # Preserve the caller's specific path (e.g. "external_llm_sql") —
        # confidence_payload() feeds used_filters and used to clobber it back
        # to a generic "sql".
        answer_path=answer_path if ok else "no_data",
        citations_verified=ok,
    )


def confidence_payload(signals: ConfidenceSignals) -> dict[str, Any]:
    return {
        "top_doc_score": signals.top_doc_score,
        "confidence_tier": signals.tier,
        "source_count": signals.source_count,
        "fallback_level": signals.fallback_level,
        "answer_path": signals.answer_path,
        "citations_verified": signals.citations_verified,
    }
