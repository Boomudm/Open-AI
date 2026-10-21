"""API key issuance and verification for external (server-to-server) integrations.

Keys look like ``nk_<48 hex chars>`` and are sent as a normal bearer token.
Only the SHA-256 digest is persisted; a key acts as its linked user, so RBAC
(roles, factory access, job positions) is resolved live from that user's rows
and cached briefly in Redis. Revoking a key or deactivating the user takes
effect within ``_CACHE_TTL_SEC`` at worst, immediately when revoked through
the admin endpoint (which busts the cache).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from spark.core.cache import Cache
from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.db.models.api_keys import ApiKey
from spark.db.models.job_positions import UserJobPosition
from spark.db.models.org import Role, User, UserFactoryAccess, UserRole

log = get_logger(__name__)

API_KEY_TOKEN_PREFIX = "nk_"

_CACHE_TTL_SEC = 60
_LAST_USED_THROTTLE_SEC = 300


def is_api_key_token(token: str) -> bool:
    return token.startswith(API_KEY_TOKEN_PREFIX)


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(plaintext, display_prefix, sha256_hex)`` for a fresh key."""
    plaintext = f"{API_KEY_TOKEN_PREFIX}{secrets.token_hex(24)}"
    return plaintext, plaintext[:11], hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _cache_key(key_hash: str) -> str:
    return f"apikey:v1:{key_hash}"


async def bust_api_key_cache(key_hash: str) -> None:
    try:
        await Cache.get().delete(_cache_key(key_hash))
    except Exception as exc:
        log.warning("api_key_cache_bust_failed", error=str(exc)[:200])


async def _load_principal_payload(key_hash: str) -> tuple[dict | None, str | None]:
    """Resolve key + linked user RBAC from the DB. Returns (payload, err_code)."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        ).scalar_one_or_none()
        if row is None:
            return None, "api_key_invalid"
        if not row.is_active:
            return None, "api_key_revoked"
        if row.expires_at is not None and row.expires_at <= datetime.now(timezone.utc):
            return None, "api_key_expired"

        user = await session.get(User, row.user_id)
        if user is None or not user.is_active:
            return None, "api_key_user_inactive"

        roles = (
            await session.execute(
                select(Role.role_code)
                .join(UserRole, UserRole.role_id == Role.role_id)
                .where(UserRole.user_id == user.user_id)
            )
        ).scalars().all()
        access_rows = (
            await session.execute(
                select(UserFactoryAccess.factory_id, UserFactoryAccess.access_level).where(
                    UserFactoryAccess.user_id == user.user_id
                )
            )
        ).all()
        position_rows = (
            await session.execute(
                select(UserJobPosition.position_id).where(UserJobPosition.user_id == user.user_id)
            )
        ).scalars().all()

        return {
            "key_id": str(row.key_id),
            "user_id": str(user.user_id),
            "username": user.username,
            "roles": list(roles),
            "factory_access": {fid: lvl for fid, lvl in access_rows},
            "job_position_ids": [str(pid) for pid in position_rows],
            "token_version": int(user.token_version),
            "privacy_policy_version": user.privacy_policy_version or "",
            "is_super_admin": bool(user.is_super_admin),
        }, None


async def _touch_last_used(key_id: str) -> None:
    """Best-effort ``last_used_at`` bump, throttled per key via Redis marker."""
    cache = Cache.get()
    marker = f"apikey:lastused:{key_id}"
    try:
        if await cache.get_json(marker):
            return
        await cache.set_json(marker, 1, ttl=_LAST_USED_THROTTLE_SEC)
    except Exception:
        return
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.key_id == uuid.UUID(key_id))
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()
    except Exception as exc:
        log.warning("api_key_last_used_update_failed", error=str(exc)[:200])


async def principal_for_api_key(token: str) -> tuple["object | None", str | None]:
    """Validate an ``nk_`` bearer token. Returns (Principal, None) or (None, err_code)."""
    from spark.core.security import Principal

    key_hash = hash_api_key(token)
    cache = Cache.get()
    payload = None
    try:
        payload = await cache.get_json(_cache_key(key_hash))
    except Exception:
        payload = None

    if payload is None:
        payload, err_code = await _load_principal_payload(key_hash)
        if payload is None:
            return None, err_code
        try:
            await cache.set_json(_cache_key(key_hash), payload, ttl=_CACHE_TTL_SEC)
        except Exception:
            pass

    await _touch_last_used(payload["key_id"])
    return (
        Principal(
            user_id=payload["user_id"],
            username=payload["username"],
            roles=tuple(payload["roles"]),
            factory_access=dict(payload["factory_access"]),
            job_position_ids=tuple(payload["job_position_ids"]),
            token_version=payload["token_version"],
            privacy_policy_version=payload["privacy_policy_version"],
            is_super_admin=payload["is_super_admin"],
        ),
        None,
    )


_API_KEY_ERROR_DETAIL = {
    "api_key_invalid": "invalid API key",
    "api_key_revoked": "API key revoked",
    "api_key_expired": "API key expired",
    "api_key_user_inactive": "API key account inactive",
}


def api_key_error_detail(code: str | None) -> str:
    return _API_KEY_ERROR_DETAIL.get(code or "", "invalid API key")
