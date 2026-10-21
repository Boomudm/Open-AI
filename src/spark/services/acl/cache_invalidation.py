"""ACL cache invalidation hooks (app-layer Phase 4)."""

from __future__ import annotations

import asyncio
import uuid

from spark.core.cache import Cache
from spark.core.logging import get_logger

log = get_logger(__name__)

_FACTORY_VERSION_PREFIX = "spark:acl:fv:"
_USER_VERSION_PREFIX = "spark:acl:uv:"
_VERSION_TTL_SEC = 7 * 86400


async def read_factory_acl_version(factory_id: str | None) -> int:
    if not factory_id:
        return 0
    raw = await Cache.get().get_json(f"{_FACTORY_VERSION_PREFIX}{factory_id}")
    if isinstance(raw, dict):
        return int(raw.get("v", 0))
    return 0


async def read_user_acl_version(user_id: str | uuid.UUID) -> int:
    raw = await Cache.get().get_json(f"{_USER_VERSION_PREFIX}{user_id}")
    if isinstance(raw, dict):
        return int(raw.get("v", 0))
    return 0


async def read_acl_versions(
    *,
    factory_id: str | None,
    user_id: str | uuid.UUID,
) -> tuple[int, int]:
    """Fetch factory + user ACL generations concurrently."""
    factory_version, user_version = await asyncio.gather(
        read_factory_acl_version(factory_id),
        read_user_acl_version(user_id),
    )
    return int(factory_version), int(user_version)


async def bump_factory_acl_version(factory_id: str | None) -> None:
    """Bump factory ACL generation after document release or ACL mutation."""
    if not factory_id:
        return
    key = f"{_FACTORY_VERSION_PREFIX}{factory_id}"
    version = await read_factory_acl_version(factory_id) + 1
    await Cache.get().set_json(key, {"v": version}, ttl=_VERSION_TTL_SEC)
    log.debug("acl_factory_version_bumped", factory_id=factory_id, version=version)


async def invalidate_user_doc_acl_cache(user_id: str | uuid.UUID) -> None:
    """Bump per-user ACL generation after role/position/factory grant change."""
    key = f"{_USER_VERSION_PREFIX}{user_id}"
    version = await read_user_acl_version(user_id) + 1
    await Cache.get().set_json(key, {"v": version}, ttl=_VERSION_TTL_SEC)
    log.debug("acl_user_version_bumped", user_id=str(user_id), version=version)
