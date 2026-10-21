"""Circuit breaker shared types (Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

OutcomeKind = Literal["success", "llm_timeout", "embed_error", "rerank_gate_fail", "vector_timeout", "unhandled"]


class CircuitDependency(str, Enum):
    EMBED = "embed"
    RERANK = "rerank"
    LLM = "llm"
    VECTOR = "vector"
    UNHANDLED = "unhandled"


class CircuitMode(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


OUTCOME_TO_DEPENDENCY: dict[OutcomeKind, CircuitDependency] = {
    "embed_error": CircuitDependency.EMBED,
    "rerank_gate_fail": CircuitDependency.RERANK,
    "llm_timeout": CircuitDependency.LLM,
    "vector_timeout": CircuitDependency.VECTOR,
    "unhandled": CircuitDependency.UNHANDLED,
    "success": CircuitDependency.LLM,
}

CRITICAL_OUTCOMES: frozenset[OutcomeKind] = frozenset(
    {"embed_error", "rerank_gate_fail", "llm_timeout", "vector_timeout", "unhandled"}
)

ALL_DEPENDENCIES: tuple[CircuitDependency, ...] = tuple(CircuitDependency)


@dataclass(frozen=True)
class CircuitDecision:
    mode: CircuitMode
    skip_llm: bool
    force_rerank_degraded: bool = False
    embed_breaker_open: bool = False
    open_dependencies: frozenset[str] = frozenset()
