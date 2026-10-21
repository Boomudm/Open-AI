from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.cache import Cache
from spark.core.config import settings
from spark.db.models.job_positions import DocumentJobPosition, UserJobPosition
from spark.db.models.org import User


def token_version_cache_key(user_id: str | uuid.UUID) -> str:
    return f"auth:token_version:{user_id}"


async def get_cached_user_auth_state(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> dict | None:
    cache = Cache.get()
    cached = await cache.get_json(token_version_cache_key(user_id))
    if cached is not None:
        return cached

    user = await session.get(User, user_id)
    if user is None:
        return None

    state = {
        "token_version": user.token_version,
        "stream_epoch": user.token_version,
        "is_active": user.is_active,
    }
    await cache.set_json(
        token_version_cache_key(user_id),
        state,
        ttl=settings.auth_token_version_cache_ttl,
    )
    return state


async def invalidate_user_auth_cache(user_id: uuid.UUID) -> None:
    cache = Cache.get()
    await cache.delete(token_version_cache_key(user_id))


async def bump_user_token_version(session: AsyncSession, user: User) -> int:
    user.token_version = (user.token_version or 0) + 1
    await invalidate_user_auth_cache(user.user_id)
    from spark.services.acl.cache_invalidation import invalidate_user_doc_acl_cache

    await invalidate_user_doc_acl_cache(user.user_id)
    return user.token_version


async def token_version_matches(
    session: AsyncSession,
    user_id: uuid.UUID,
    claim_version: int,
) -> bool:
    """Return True when JWT token_version matches the live user record."""
    state = await get_cached_user_auth_state(session, user_id)
    if state is None or not state.get("is_active", True):
        return False
    return int(state.get("token_version", 0)) == claim_version


async def count_position_usage(session: AsyncSession, position_id: uuid.UUID) -> tuple[int, int]:
    doc_count = await session.scalar(
        select(func.count())
        .select_from(DocumentJobPosition)
        .where(DocumentJobPosition.position_id == position_id)
    )
    user_count = await session.scalar(
        select(func.count())
        .select_from(UserJobPosition)
        .where(UserJobPosition.position_id == position_id)
    )
    return int(doc_count or 0), int(user_count or 0)
