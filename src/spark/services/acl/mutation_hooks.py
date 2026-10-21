"""Single entry for ACL-affecting writes (app-layer v2 Phase 4)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.services.acl.cache_invalidation import (
    bump_factory_acl_version,
    invalidate_user_doc_acl_cache,
)
from spark.services.acl.factory_doc_index import add_factory_doc

log = get_logger(__name__)


def _audit_acl_invalidation(
    *,
    reason: str,
    factory_id: str | None = None,
    user_id: str | uuid.UUID | None = None,
    doc_id: uuid.UUID | None = None,
) -> None:
    log.info(
        "acl_cache_invalidated",
        reason=reason,
        factory_id=factory_id,
        user_id=str(user_id) if user_id is not None else None,
        doc_id=str(doc_id) if doc_id is not None else None,
    )


async def on_document_positions_changed(
    session: AsyncSession,
    *,
    factory_id: str | None,
    doc_id: uuid.UUID,
    position_ids: list[uuid.UUID],
) -> None:
    """Document visibility / job-position scope changed."""
    del session, position_ids  # session reserved for future audit rows
    if factory_id:
        await bump_factory_acl_version(factory_id)
        await add_factory_doc(factory_id, doc_id)
    _audit_acl_invalidation(
        reason="document_positions_changed",
        factory_id=factory_id,
        doc_id=doc_id,
    )


async def on_document_released(
    session: AsyncSession,
    *,
    factory_id: str | None,
    doc_id: uuid.UUID,
) -> None:
    """Quarantined document approved for indexing."""
    del session
    if factory_id:
        await bump_factory_acl_version(factory_id)
        await add_factory_doc(factory_id, doc_id)
    _audit_acl_invalidation(
        reason="document_released",
        factory_id=factory_id,
        doc_id=doc_id,
    )


async def on_user_factory_access_changed(
    session: AsyncSession,
    *,
    user_id: str | uuid.UUID,
    factory_id: str | None,
) -> None:
    """User factory grant added, removed, or level changed."""
    del session
    await invalidate_user_doc_acl_cache(user_id)
    _audit_acl_invalidation(
        reason="user_factory_access_changed",
        user_id=user_id,
        factory_id=factory_id,
    )


async def on_user_positions_changed(
    session: AsyncSession,
    *,
    user_id: str | uuid.UUID,
) -> None:
    """User job-position assignment changed."""
    del session
    await invalidate_user_doc_acl_cache(user_id)
    _audit_acl_invalidation(reason="user_positions_changed", user_id=user_id)
