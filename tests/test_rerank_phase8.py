"""Phase 8 rerank pipeline — gates, degraded calibration, cache, circuit metrics."""

from __future__ import annotations

import pytest

from spark.retrieval.intent.router import IntentRouter, QueryIntent
from spark.retrieval.rerank.gate import apply_rerank_gate
from spark.retrieval.rerank.gates_config import load_rerank_gates_config
from spark.retrieval.safety.circuit_breaker import record_rag_outcome
from spark.retrieval.models import RetrievedDoc


def _doc(score: float, *, chunk_id: str = "c1") -> RetrievedDoc:
    return RetrievedDoc(
        page_content="bearing temperature limit",
        score=score,
        vector_score=score,
        fusion_score=score,
        payload={"chunk_id": chunk_id, "document_type": "machine_manual"},
    )


def test_rerank_gates_yaml_loads_intent_thresholds() -> None:
    # Pin the default (bge-tuned) file: with no path the loader picks the
    # Forge-tuned variant whenever the ambient env has Forge rerank active.
    from pathlib import Path

    import spark

    default_yaml = Path(spark.__file__).resolve().parents[2] / "configs" / "retrieval" / "rerank_gates.yaml"
    cfg = load_rerank_gates_config(str(default_yaml))
    loto = cfg.for_intent(QueryIntent.SAFETY_LOTO)
    assert loto.max == pytest.approx(0.50)
    assert loto.avg == pytest.approx(0.40)


def test_rerank_gate_fail_recorded_when_circuit_enabled() -> None:
    docs = [_doc(0.20), _doc(0.18, chunk_id="c2")]
    plan = IntentRouter().route("LOTO lockout breaker MC-001")
    result = apply_rerank_gate(
        docs,
        intent_plan=plan,
        circuit_enabled=True,
    )
    assert result.passed is False


def test_degraded_gate_fails_weak_fusion_without_calibration() -> None:
    """Raw fusion floors replace dangerous min-max calibration."""
    from spark.retrieval.degraded_types import DegradedRetrievalPolicy
    from spark.retrieval.rerank.gate import apply_rerank_gate

    docs = [
        _doc(0.12, chunk_id="c1"),
        _doc(0.11, chunk_id="c2"),
        _doc(0.10, chunk_id="c3"),
    ]
    result = apply_rerank_gate(
        docs,
        question="bearing temperature MC-001",
        degraded=True,
        degraded_policy=DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK,
    )
    assert result.passed is False


@pytest.mark.asyncio
async def test_rerank_cache_misses_after_ingest_generation_change() -> None:
    from spark.core.cache import Cache
    from spark.retrieval.rerank.cache import get_cached_rerank_scores, store_rerank_scores

    cache = Cache.get()
    await cache.set_json("rerank:test", {"v": 1}, ttl=60)

    session_id = "sess-phase8"
    question = "cooling fan temperature"
    chunk_id = "chunk-abc"

    await store_rerank_scores(
        session_id,
        question,
        {chunk_id: 0.88},
        generations_by_chunk={chunk_id: 1},
    )
    hit_gen1 = await get_cached_rerank_scores(
        session_id,
        question,
        [chunk_id],
        generations=[1],
    )
    miss_gen2 = await get_cached_rerank_scores(
        session_id,
        question,
        [chunk_id],
        generations=[2],
    )
    assert hit_gen1.get(chunk_id) == pytest.approx(0.88)
    assert chunk_id not in miss_gen2


def test_record_rerank_gate_fail_outcome_kind() -> None:
    record_rag_outcome("rerank_gate_fail", enabled=True)
