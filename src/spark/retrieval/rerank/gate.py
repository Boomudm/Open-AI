"""Rerank relevance gate with circuit-breaker outcome recording."""

from __future__ import annotations

from dataclasses import dataclass

from spark.core.metrics import rag_rerank_gate_fail_total
from spark.retrieval.degraded_types import DegradedRetrievalPolicy, raw_fusion_score
from spark.retrieval.intent.router import IntentPlan, QueryIntent
from spark.retrieval.degraded_floors_config import load_degraded_fusion_floors
from spark.retrieval.rerank.gates_config import GateThresholds, thresholds_for_intent
from spark.retrieval.common import log
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.tuning import RagTuningContext


@dataclass(frozen=True)
class GateResult:
    passed: bool
    max_score: float
    avg_top3: float
    thresholds: GateThresholds
    degraded: bool = False
    degraded_policy: DegradedRetrievalPolicy | None = None


def _score_stats(docs: list[RetrievedDoc]) -> tuple[float, float]:
    scores = [float(d.score) for d in docs]
    max_score = max(scores)
    top3 = sorted(scores, reverse=True)[:3]
    avg = sum(top3) / len(top3)
    return max_score, avg


def _fusion_rank_stats(docs: list[RetrievedDoc]) -> tuple[float, float, int]:
    """Return top raw fusion, gap to second, and 1-based rank of the leading doc."""
    if not docs:
        return 0.0, 0.0, 99
    ranked = sorted(docs, key=raw_fusion_score, reverse=True)
    top_raw = raw_fusion_score(ranked[0])
    second_raw = raw_fusion_score(ranked[1]) if len(ranked) > 1 else 0.0
    return top_raw, top_raw - second_raw, 1


def _apply_degraded_gate(
    docs: list[RetrievedDoc],
    *,
    intent: QueryIntent,
    degraded_policy: DegradedRetrievalPolicy | None = None,
) -> GateResult:
    floors = load_degraded_fusion_floors()
    spec = floors.for_intent(intent)
    top_raw, rank_gap, top_rank = _fusion_rank_stats(docs)

    rank_ok = top_rank <= spec.max_fusion_rank
    gap_ok = rank_gap >= spec.min_rank_gap
    floor_ok = top_raw >= spec.min_raw_fusion
    passed = rank_ok and (gap_ok or floor_ok)

    if degraded_policy == DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN:
        passed = False

    thresholds = GateThresholds(max=spec.min_raw_fusion, avg=spec.min_rank_gap)
    log.info(
        "rag_relevance_degraded",
        top_raw_fusion=round(top_raw, 4),
        rank_gap=round(rank_gap, 4),
        top_rank=top_rank,
        count=len(docs),
        intent=intent.value,
        policy=degraded_policy.value if degraded_policy else None,
        passed=passed,
    )
    return GateResult(
        passed=passed,
        max_score=top_raw,
        avg_top3=rank_gap,
        thresholds=thresholds,
        degraded=True,
        degraded_policy=degraded_policy,
    )


def _record_gate_fail(*, intent: QueryIntent, degraded: bool) -> None:
    rag_rerank_gate_fail_total.labels(
        intent=intent.value,
        degraded="true" if degraded else "false",
    ).inc()


def apply_rerank_gate(
    docs: list[RetrievedDoc],
    *,
    question: str | None = None,
    intent_plan: IntentPlan | None = None,
    tuning: RagTuningContext | None = None,
    circuit_enabled: bool = False,
    degraded: bool = False,
    degraded_policy: DegradedRetrievalPolicy | None = None,
    factory_id: str | None = None,
) -> GateResult:
    """Evaluate rerank scores against intent-aware thresholds."""
    if intent_plan is None and question:
        from spark.retrieval.intent.router import IntentRouter

        intent_plan = IntentRouter().route(question)

    intent = intent_plan.intent if intent_plan else QueryIntent.GENERAL

    if not docs:
        if circuit_enabled:
            from spark.retrieval.safety.circuit_breaker import record_rag_outcome

            record_rag_outcome(
                "rerank_gate_fail",
                enabled=circuit_enabled,
                factory_id=factory_id,
            )
        _record_gate_fail(intent=intent, degraded=degraded)
        return GateResult(
            passed=False,
            max_score=0,
            avg_top3=0,
            thresholds=thresholds_for_intent(QueryIntent.GENERAL),
            degraded=degraded,
            degraded_policy=degraded_policy,
        )

    if degraded:
        result = _apply_degraded_gate(docs, intent=intent, degraded_policy=degraded_policy)
        if not result.passed:
            if circuit_enabled:
                from spark.retrieval.safety.circuit_breaker import record_rag_outcome

                record_rag_outcome(
                    "rerank_gate_fail",
                    enabled=circuit_enabled,
                    factory_id=factory_id,
                )
            _record_gate_fail(intent=intent, degraded=True)
        return result

    thresholds = thresholds_for_intent(
        intent,
        tuning_max=tuning.min_max_score if tuning else None,
        tuning_avg=tuning.min_avg_score if tuning else None,
    )
    if intent_plan and intent_plan.min_rerank_score is not None:
        thresholds = GateThresholds(
            max=max(thresholds.max, float(intent_plan.min_rerank_score)),
            avg=thresholds.avg,
        )

    max_score, avg = _score_stats(docs)
    passed = max_score >= thresholds.max and avg >= thresholds.avg
    log.info(
        "rag_relevance",
        max_score=round(max_score, 4),
        avg_top3=round(avg, 4),
        count=len(docs),
        intent=intent.value,
        degraded=False,
        passed=passed,
    )
    if not passed and circuit_enabled:
        from spark.retrieval.safety.circuit_breaker import record_rag_outcome

        record_rag_outcome(
            "rerank_gate_fail",
            enabled=circuit_enabled,
            factory_id=factory_id,
        )
    if not passed:
        _record_gate_fail(intent=intent, degraded=False)

    return GateResult(
        passed=passed,
        max_score=max_score,
        avg_top3=avg,
        thresholds=thresholds,
        degraded=False,
        degraded_policy=DegradedRetrievalPolicy.CE_ACTIVE,
    )


def passes_authoritative_relevance_gate(
    docs: list[RetrievedDoc],
    *,
    min_max_score: float | None = None,
    min_avg_score: float | None = None,
    question: str | None = None,
    tuning: RagTuningContext | None = None,
    intent_plan: IntentPlan | None = None,
    circuit_enabled: bool = False,
    degraded: bool = False,
    degraded_policy: DegradedRetrievalPolicy | None = None,
    factory_id: str | None = None,
) -> bool:
    """Backward-compatible bool wrapper used by RAGService."""
    if min_max_score is not None or min_avg_score is not None:
        thresholds = GateThresholds(
            max=min_max_score if min_max_score is not None else 0.35,
            avg=min_avg_score if min_avg_score is not None else 0.25,
        )
        if not docs:
            return False
        max_score, avg = _score_stats(docs)
        log.info(
            "rag_relevance",
            max_score=round(max_score, 4),
            avg_top3=round(avg, 4),
            count=len(docs),
        )
        return max_score >= thresholds.max and avg >= thresholds.avg

    return apply_rerank_gate(
        docs,
        question=question,
        intent_plan=intent_plan,
        tuning=tuning,
        circuit_enabled=circuit_enabled,
        degraded=degraded,
        degraded_policy=degraded_policy,
        factory_id=factory_id,
    ).passed
