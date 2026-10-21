"""RAG-only stub — user-facing agentic canary path disabled."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SafetyOverrideDecision:
    override: bool
    reason: str = ""


def should_serve_agentic(_session_id: uuid.UUID) -> bool:
    return False


def evaluate_safety_override(_question: str, _agentic: dict[str, Any]) -> SafetyOverrideDecision:
    return SafetyOverrideDecision(False)


def log_safety_override(_question: str, _reason: str) -> None:
    return None


def record_agentic_outcome(_agentic: dict[str, Any] | None, *, agentic_error: str | None = None) -> None:
    return None
