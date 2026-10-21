"""RAG scope-broadening audit persistence (Phase 10)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from spark.core.logging import get_logger
from spark.retrieval.models import RAGFilter

log = get_logger(__name__)


async def persist_scope_broadening_audit(
    *,
    question: str,
    fallback_level: int,
    original_rf: RAGFilter,
    active_rf: RAGFilter,
    user_id: uuid.UUID | str | None = None,
    allow_scope_broadening: bool,
) -> None:
    """Persist audit row when fallback broadened scope with explicit user consent."""
    if fallback_level <= 0 or not allow_scope_broadening:
        return

    payload = {
        "fallback_level": fallback_level,
        "factory_id": original_rf.factory_id,
        "allow_scope_broadening": allow_scope_broadening,
    }
    log.info(
        "rag_scope_broadened",
        question=question[:120],
        **payload,
    )

    try:
        from spark.core.database import AsyncSessionLocal
        from spark.db.models.rag_audit import RagScopeBroadeningAudit

        uid: uuid.UUID | None = None
        if user_id is not None:
            uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        row = RagScopeBroadeningAudit(
            user_id=uid,
            factory_id=original_rf.factory_id,
            question=question[:4000],
            fallback_level=fallback_level,
            original_filter=_filter_dict(original_rf),
            broadened_filter=_filter_dict(active_rf),
        )
        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception as exc:
        log.warning(
            "rag_scope_broadening_audit_failed",
            error=str(exc)[:200],
            fallback_level=fallback_level,
        )

    from spark.audit.worm_sink import schedule_worm_audit

    schedule_worm_audit(
        "rag_scope_broadened",
        actor_id=str(user_id) if user_id is not None else None,
        factory_id=original_rf.factory_id,
        payload={
            "fallback_level": fallback_level,
            "question": question[:400],
            "original_filter": _filter_dict(original_rf),
            "broadened_filter": _filter_dict(active_rf),
            "allow_scope_broadening": allow_scope_broadening,
        },
    )


def _filter_dict(rf: RAGFilter) -> dict[str, Any]:
    return {k: v for k, v in asdict(rf).items() if v not in (None, False)}
