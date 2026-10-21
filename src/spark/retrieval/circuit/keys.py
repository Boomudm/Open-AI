"""Redis key helpers for factory-scoped RAG circuit breakers (Phase 8)."""

from __future__ import annotations

from spark.retrieval.circuit.factory_scope import normalize_factory_id


def outcome_key(factory_id: str | None, dependency: str) -> str:
    fid = normalize_factory_id(factory_id)
    return f"spark:rag:{fid}:circuit:{dependency}:outcomes"


def open_key(factory_id: str | None, dependency: str) -> str:
    fid = normalize_factory_id(factory_id)
    return f"spark:rag:{fid}:circuit:{dependency}:open"


def probe_key(factory_id: str | None, dependency: str) -> str:
    fid = normalize_factory_id(factory_id)
    return f"spark:rag:{fid}:circuit:{dependency}:probe"
