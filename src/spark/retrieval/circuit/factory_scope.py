"""Factory tenancy helpers for circuit breaker isolation (Phase 8)."""

from __future__ import annotations

DEFAULT_FACTORY_ID = "global"


def normalize_factory_id(factory_id: str | None) -> str:
    if factory_id and str(factory_id).strip():
        return str(factory_id).strip()
    return DEFAULT_FACTORY_ID
