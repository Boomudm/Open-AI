"""Cooperative request deadline budget for RAG kernel stages (Phase 10)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from spark.core.config import settings


@dataclass(frozen=True)
class RequestDeadline:
    started_at: float
    budget_ms: int

    @classmethod
    def from_settings(cls, *, started_at: float | None = None) -> RequestDeadline:
        budget = int(getattr(settings, "rag_request_budget_ms", 30_000) or 30_000)
        return cls(started_at=started_at if started_at is not None else time.perf_counter(), budget_ms=budget)

    def remaining_ms(self) -> int:
        elapsed_ms = int((time.perf_counter() - self.started_at) * 1000)
        return max(0, self.budget_ms - elapsed_ms)

    def expired(self) -> bool:
        return self.remaining_ms() <= 0
