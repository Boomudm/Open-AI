"""Online quality feedback logging foundation (Phase 15)."""

from __future__ import annotations

import uuid
from typing import Any

from spark.core.logging import get_logger

log = get_logger(__name__)


def log_online_feedback(
    *,
    query_id: str | uuid.UUID,
    fallback_level: int,
    citations_verified: bool,
    user_feedback: str | None = None,
    factory_id: str | None = None,
    answer_path: str | None = None,
    intent: str | None = None,
    classifier_confidence: float | None = None,
    route_source: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append-only structured log for future tuning — no ML training in Phase 15."""
    payload: dict[str, Any] = {
        "query_id": str(query_id),
        "fallback_level": fallback_level,
        "citations_verified": citations_verified,
        "factory_id": factory_id,
        "answer_path": answer_path,
    }
    if intent is not None:
        payload["intent"] = intent
    if classifier_confidence is not None:
        payload["classifier_confidence"] = classifier_confidence
    if route_source is not None:
        payload["route_source"] = route_source
    if user_feedback:
        payload["user_feedback"] = user_feedback[:500]
    if extra:
        payload.update(extra)
    log.info("online_feedback", **payload)
