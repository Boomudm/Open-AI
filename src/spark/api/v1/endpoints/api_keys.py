"""Admin management of API keys for external integrations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.database import get_session
from spark.core.security import Principal, require_role
from spark.db.models.api_keys import ApiKey
from spark.db.models.org import User
from spark.services.api_key_service import bust_api_key_cache, generate_api_key

router = APIRouter(prefix="/admin/api-keys", tags=["Admin"])


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["partner-website"])
    user_id: uuid.UUID = Field(
        description="Service-account user the key acts as (its roles/factory access apply)"
    )
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    key_id: uuid.UUID
    name: str
    key_prefix: str
    user_id: uuid.UUID
    username: str | None = None
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    api_key: str = Field(description="Full key — shown only once; store it securely")


def _to_out(row: ApiKey, username: str | None = None) -> ApiKeyOut:
    return ApiKeyOut(
        key_id=row.key_id,
        name=row.name,
        key_prefix=row.key_prefix,
        user_id=row.user_id,
        username=username,
        is_active=row.is_active,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


@router.post("", response_model=ApiKeyCreatedOut, status_code=201, responses=WRITE_ERRORS)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    session: AsyncSession = Depends(get_session),
    p: Principal = Depends(require_role("admin")),
) -> ApiKeyCreatedOut:
    user = await session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if not user.is_active:
        raise HTTPException(409, "user is inactive")
    if payload.expires_at is not None and payload.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "expires_at must be in the future")

    plaintext, prefix, key_hash = generate_api_key()
    created_by: uuid.UUID | None = None
    try:
        creator_id = uuid.UUID(p.user_id)
        if await session.get(User, creator_id) is not None:
            created_by = creator_id
    except ValueError:
        pass
    row = ApiKey(
        name=payload.name.strip(),
        key_prefix=prefix,
        key_hash=key_hash,
        user_id=user.user_id,
        created_by=created_by,
        expires_at=payload.expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    out = _to_out(row, username=user.username)
    return ApiKeyCreatedOut(**out.model_dump(), api_key=plaintext)


@router.get("", response_model=list[ApiKeyOut], responses=READ_ERRORS)
async def list_api_keys(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> list[ApiKeyOut]:
    rows = (
        await session.execute(
            select(ApiKey, User.username)
            .join(User, User.user_id == ApiKey.user_id)
            .order_by(ApiKey.created_at.desc())
        )
    ).all()
    return [_to_out(row, username=username) for row, username in rows]


@router.post("/{key_id}/revoke", response_model=ApiKeyOut, responses=WRITE_ERRORS)
async def revoke_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> ApiKeyOut:
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(404, "API key not found")
    if row.is_active:
        row.is_active = False
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
    await bust_api_key_cache(row.key_hash)
    user = await session.get(User, row.user_id)
    return _to_out(row, username=user.username if user else None)


@router.delete("/{key_id}", status_code=204, response_class=Response, responses=WRITE_ERRORS)
async def delete_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> Response:
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(404, "API key not found")
    key_hash = row.key_hash
    await session.delete(row)
    await session.commit()
    await bust_api_key_cache(key_hash)
    return Response(status_code=204)
