"""Resolve per-dependency circuit decisions for RAG entry (Phase 8)."""

from __future__ import annotations

from spark.retrieval.circuit.dependency_breaker import (
    allow_half_open_probe,
    is_dependency_open,
    read_admin_flag,
)
from spark.retrieval.circuit.factory_scope import normalize_factory_id
from spark.retrieval.circuit.types import (
    ALL_DEPENDENCIES,
    CircuitDecision,
    CircuitDependency,
    CircuitMode,
)


async def resolve_circuit_decision(
    *,
    enabled: bool,
    factory_id: str | None,
) -> CircuitDecision:
    """Bulkhead resolution — each dependency trips independently."""
    if not enabled:
        return CircuitDecision(mode=CircuitMode.CLOSED, skip_llm=False)

    fid = normalize_factory_id(factory_id)
    if read_admin_flag() is not None:
        return CircuitDecision(
            mode=CircuitMode.OPEN,
            skip_llm=True,
            open_dependencies=frozenset(d.value for d in ALL_DEPENDENCIES),
        )

    open_deps: set[str] = set()
    half_open_dep: str | None = None

    for dep in ALL_DEPENDENCIES:
        if not await is_dependency_open(fid, dep):
            continue
        open_deps.add(dep.value)
        if half_open_dep is None and await allow_half_open_probe(fid, dep):
            half_open_dep = dep.value

    skip_llm = CircuitDependency.LLM.value in open_deps and half_open_dep != CircuitDependency.LLM.value
    force_rerank_degraded = (
        CircuitDependency.RERANK.value in open_deps
        and half_open_dep != CircuitDependency.RERANK.value
    )
    embed_breaker_open = (
        CircuitDependency.EMBED.value in open_deps
        and half_open_dep != CircuitDependency.EMBED.value
    )

    if not open_deps:
        return CircuitDecision(mode=CircuitMode.CLOSED, skip_llm=False)

    if half_open_dep is not None:
        return CircuitDecision(
            mode=CircuitMode.HALF_OPEN,
            skip_llm=False,
            force_rerank_degraded=False,
            embed_breaker_open=False,
            open_dependencies=frozenset(open_deps),
        )

    return CircuitDecision(
        mode=CircuitMode.OPEN,
        skip_llm=skip_llm,
        force_rerank_degraded=force_rerank_degraded,
        embed_breaker_open=embed_breaker_open,
        open_dependencies=frozenset(open_deps),
    )
