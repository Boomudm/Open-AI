"""RAG-only stub — legacy shadow/agentic comparison logging disabled."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShadowLegacySnapshot:
    question: str
    legacy_route: str | None = None
    legacy_answer: str = ""
    legacy_sources: list[dict[str, Any]] = field(default_factory=list)
    routing_reason: str | None = None
    legacy_cache_hit: bool = False
    message_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    effective_question: str | None = None
    factory_id: str | None = None
    machine_id: str | None = None
    document_type: str | None = None
    filter_fingerprint: str | None = None
    legacy_cache_id: uuid.UUID | None = None
    legacy_answer_path: str | None = None
    legacy_latency_ms: float = 0.0
    allowed_doc_ids: list[str] | None = None
    allowed_factory_ids: list[str] | None = None


def schedule_agentic_shadow(_snap: ShadowLegacySnapshot) -> None:
    return None


async def persist_agentic_canary_log(**_kwargs: Any) -> None:
    return None
