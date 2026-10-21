"""Cached document ACL materialization (app-layer Phase 4).

When ``settings.rag_acl_filter_mode == "payload_acl"``, Qdrant payload filters are the
authoritative retrieval ACL boundary; this Redis cache is advisory for app-layer paths only.
"""

from __future__ import annotations

import hashlib
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.cache import Cache
from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import acl_cache_miss_duration_seconds
from spark.core.security import Principal
from spark.services.acl.cache_invalidation import read_acl_versions
from spark.services.document_access_service import compute_allowed_doc_ids

log = get_logger(__name__)

_CACHE_PREFIX = "spark:acl:docs:"


def _positions_hash(principal: Principal) -> str:
    joined = ",".join(sorted(str(x) for x in principal.job_position_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def _cache_key(
    principal: Principal,
    *,
    factory_id: str | None,
    factory_version: int,
    user_version: int,
) -> str:
    factory_scope = factory_id or "*"
    return (
        f"{_CACHE_PREFIX}{principal.user_id}:{principal.token_version}:"
        f"{factory_scope}:{_positions_hash(principal)}:fv{factory_version}:uv{user_version}"
    )


async def allowed_doc_ids_for_principal_cached(
    session: AsyncSession,
    principal: Principal,
    *,
    factory_id: str | None = None,
) -> list[uuid.UUID] | None:
    """Return allowed doc IDs, or None when admin (no Qdrant doc_id filter)."""
    if principal.is_admin:
        return None

    if settings.rag_acl_filter_mode == "payload_acl":
        return None

    factory_version, user_version = await read_acl_versions(
        factory_id=factory_id,
        user_id=principal.user_id,
    )
    key = _cache_key(
        principal,
        factory_id=factory_id,
        factory_version=factory_version,
        user_version=user_version,
    )
    ttl = max(60, int(settings.acl_cache_ttl_sec))

    cache = Cache.get()
    cached = await cache.get_json(key)
    if isinstance(cached, dict) and "doc_ids" in cached:
        ids = cached.get("doc_ids")
        if ids is None:
            return None
        if isinstance(ids, list):
            return [uuid.UUID(str(item)) for item in ids]

    started = time.perf_counter()
    doc_ids = await compute_allowed_doc_ids(session, principal, factory_id=factory_id)
    acl_cache_miss_duration_seconds.observe(time.perf_counter() - started)

    post_versions = await read_acl_versions(
        factory_id=factory_id,
        user_id=principal.user_id,
    )
    if post_versions != (factory_version, user_version):
        log.debug(
            "acl_cache_version_race",
            user_id=principal.user_id,
            factory_id=factory_id,
            before=factory_version,
            after=post_versions[0],
        )
        return await compute_allowed_doc_ids(session, principal, factory_id=factory_id)

    payload = {
        "doc_ids": None if doc_ids is None else [str(item) for item in doc_ids],
    }
    await cache.set_json(key, payload, ttl=ttl)
    return doc_ids
