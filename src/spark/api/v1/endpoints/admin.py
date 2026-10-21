from __future__ import annotations

import asyncio
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.auth import hash_password
from spark.core.database import get_session
from spark.core.security import Principal, get_principal, require_role, require_super_admin
from spark.db.models.job_positions import JobPosition
from spark.db.models.org import Factory, Role, User, UserFactoryAccess, UserRole
from spark.schemas.factories import FactoryAdmin, FactoryCreate
from spark.schemas.factory_settings import FactorySettingsPatch, FactorySettingsResponse
from spark.schemas.job_positions import (
    AdminUserBrief,
    AdminUserCreate,
    AdminUserUpdate,
    FactoryAccessEntry,
    JobPositionAdmin,
    JobPositionCreate,
    JobPositionUpdate,
    JobPositionUsage,
)
from spark.schemas.pagination import PaginatedResponse
from spark.services.admin_user_service import (
    count_position_usage_batch,
    load_admin_users_batch,
    load_job_positions_admin_batch,
)
from spark.services.auth_session import bump_user_token_version
from spark.services.job_position_service import set_user_job_positions
from spark.services.master_data_service import MasterDataService
from spark.services.factory_config_service import factory_config_service

router = APIRouter(prefix="/admin", tags=["Admin"])

master_data_service = MasterDataService()

_POSITION_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")
_ALLOWED_ROLES = frozenset({"employee", "operator", "admin"})


def _normalize_position_code(code: str) -> str:
    normalized = code.strip().lower().replace(" ", "_").replace("-", "_")
    if not _POSITION_CODE_RE.match(normalized):
        raise HTTPException(422, "position_code must be lowercase slug (a-z, 0-9, _)")
    return normalized


async def _load_admin_user(session: AsyncSession, user: User) -> AdminUserBrief:
    items = await load_admin_users_batch(session, [user])
    return items[0]


async def _set_user_role(session: AsyncSession, user: User, role_code: str) -> None:
    if role_code not in _ALLOWED_ROLES:
        raise HTTPException(422, f"invalid role: {role_code}")
    role = await session.scalar(select(Role).where(Role.role_code == role_code))
    if role is None:
        raise HTTPException(422, f"role not found: {role_code}")
    await session.execute(delete(UserRole).where(UserRole.user_id == user.user_id))
    session.add(UserRole(user_id=user.user_id, role_id=role.role_id))


async def _set_user_factory_access(
    session: AsyncSession,
    user: User,
    entries: list[FactoryAccessEntry],
) -> None:
    from spark.services.acl.mutation_hooks import on_user_factory_access_changed

    await session.execute(delete(UserFactoryAccess).where(UserFactoryAccess.user_id == user.user_id))
    for entry in entries:
        session.add(
            UserFactoryAccess(
                user_id=user.user_id,
                factory_id=entry.factory_id,
                access_level=entry.access_level,
            )
        )
    for entry in entries:
        await on_user_factory_access_changed(
            session,
            user_id=user.user_id,
            factory_id=entry.factory_id,
        )
    if not entries:
        await on_user_factory_access_changed(
            session,
            user_id=user.user_id,
            factory_id=None,
        )


def _factory_to_admin(row: Factory) -> FactoryAdmin:
    return FactoryAdmin(
        factory_id=row.factory_id,
        factory_name=row.factory_name,
        location=row.location,
        created_at=row.created_at,
    )


def _ensure_qdrant_for_factory_sync(factory_id: str) -> None:
    from spark.core.logging import get_logger
    from spark.core.qdrant import ensure_collection
    from spark.core.qdrant_strategy import list_search_collections

    log = get_logger(__name__)
    try:
        for coll in list_search_collections(factory_id):
            ensure_collection(coll)
    except Exception as exc:
        log.warning("factory_qdrant_setup_skipped", factory_id=factory_id, error=str(exc))


async def _ensure_qdrant_for_factory(factory_id: str) -> None:
    await asyncio.to_thread(_ensure_qdrant_for_factory_sync, factory_id)


@router.get("/factories", response_model=list[FactoryAdmin])
async def list_factories_admin(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> list[FactoryAdmin]:
    rows = await master_data_service.list_factories(session)
    return [_factory_to_admin(row) for row in rows]


@router.post("/factories", response_model=FactoryAdmin, status_code=201)
async def create_factory_admin(
    payload: FactoryCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> FactoryAdmin:
    try:
        row = await master_data_service.create_factory(
            session,
            factory_id=payload.factory_id,
            factory_name=payload.factory_name,
            location=payload.location,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(409, "factory already exists") from exc
        raise HTTPException(422, "invalid factory data") from exc
    await _ensure_qdrant_for_factory(row.factory_id)
    return _factory_to_admin(row)


@router.delete("/factories/{factory_id}", status_code=204, response_class=Response)
async def delete_factory_admin(
    factory_id: str,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_super_admin()),
) -> Response:
    try:
        await master_data_service.delete_factory(session, factory_id=factory_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(404, msg) from exc
        if "not empty" in msg:
            raise HTTPException(409, msg) from exc
        raise HTTPException(422, msg) from exc
    return Response(status_code=204)


@router.get("/factories/{factory_id}/settings", response_model=FactorySettingsResponse)
async def get_factory_settings(
    factory_id: str,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> FactorySettingsResponse:
    factory = await session.get(Factory, factory_id)
    if factory is None:
        raise HTTPException(404, "factory not found")
    stored = await factory_config_service.get_raw(session, factory_id)
    effective = await factory_config_service.resolve(session, factory_id)
    return FactorySettingsResponse(
        factory_id=factory_id,
        effective=effective,
        stored=stored,
    )


@router.patch("/factories/{factory_id}/settings", response_model=FactorySettingsResponse)
async def patch_factory_settings(
    factory_id: str,
    payload: FactorySettingsPatch,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> FactorySettingsResponse:
    factory = await session.get(Factory, factory_id)
    if factory is None:
        raise HTTPException(404, "factory not found")
    patch = payload.model_dump(exclude_none=True, by_alias=True)
    if not patch:
        raise HTTPException(422, "empty settings patch")
    await factory_config_service.upsert(session, factory_id, patch)
    await session.commit()
    stored = await factory_config_service.get_raw(session, factory_id)
    effective = await factory_config_service.resolve(session, factory_id)
    return FactorySettingsResponse(
        factory_id=factory_id,
        effective=effective,
        stored=stored,
    )


async def _unique_username_from_email(session: AsyncSession, email: str) -> str:
    local = email.split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_").lower()
    base = (base or "user")[:46]
    for n in range(1, 1000):
        candidate = base if n == 1 else f"{base[:46 - len(f'_{n}')]}{f'_{n}'}"
        exists = await session.scalar(select(User).where(User.username == candidate))
        if not exists:
            return candidate
    raise HTTPException(422, "could not allocate username")


@router.post("/users", response_model=AdminUserBrief, status_code=201)
async def create_user(
    payload: AdminUserCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> AdminUserBrief:
    email = payload.email.strip().lower()
    existing_email = await session.scalar(
        select(User).where(func.lower(User.email) == email)
    )
    if existing_email:
        raise HTTPException(409, "email already registered")

    username = payload.username.strip() if payload.username else None
    if username:
        taken = await session.scalar(select(User).where(User.username == username))
        if taken:
            raise HTTPException(409, "username already taken")
    else:
        username = await _unique_username_from_email(session, email)

    user = User(
        username=username,
        full_name=payload.full_name.strip() if payload.full_name else None,
        email=email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    await _set_user_role(session, user, payload.role)
    if payload.factory_access:
        await _set_user_factory_access(session, user, payload.factory_access)
    if payload.job_position_ids:
        await set_user_job_positions(session, user, payload.job_position_ids)

    await session.commit()
    await session.refresh(user)
    return await _load_admin_user(session, user)


@router.get("/users", response_model=PaginatedResponse[AdminUserBrief])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> PaginatedResponse[AdminUserBrief]:
    total = int((await session.execute(select(func.count()).select_from(User))).scalar_one())
    offset = (page - 1) * page_size
    users = (
        await session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()
    items = await load_admin_users_batch(session, list(users))
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.patch("/users/{user_id}", response_model=AdminUserBrief)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> AdminUserBrief:
    actor = get_principal(request)
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")

    if payload.is_super_admin is not None and not actor.is_super_admin:
        raise HTTPException(403, "only super admins may grant or revoke super admin access")

    changed = False
    if payload.is_active is not None:
        user.is_active = payload.is_active
        changed = True
    if payload.is_super_admin is not None:
        user.is_super_admin = payload.is_super_admin
        changed = True
    if payload.role is not None:
        await _set_user_role(session, user, payload.role)
        changed = True
    if payload.factory_access is not None:
        await _set_user_factory_access(session, user, payload.factory_access)
        changed = True
    if payload.job_position_ids is not None:
        await set_user_job_positions(session, user, payload.job_position_ids)
        changed = True

    if changed:
        await bump_user_token_version(session, user)

    await session.commit()
    await session.refresh(user)
    return await _load_admin_user(session, user)


@router.post("/users/{user_id}/promote-operator", response_model=AdminUserBrief)
async def promote_operator(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> AdminUserBrief:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")

    await _set_user_role(session, user, "operator")
    access_rows = (
        await session.execute(
            select(UserFactoryAccess).where(UserFactoryAccess.user_id == user.user_id)
        )
    ).scalars().all()
    if access_rows:
        for row in access_rows:
            if row.access_level == "read":
                row.access_level = "write"
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _load_admin_user(session, user)


@router.get("/job-positions", response_model=list[JobPositionAdmin])
async def list_job_positions_admin(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> list[JobPositionAdmin]:
    rows = (
        await session.execute(select(JobPosition).order_by(JobPosition.sort_order, JobPosition.name_th))
    ).scalars().all()
    return await load_job_positions_admin_batch(session, list(rows))


@router.post("/job-positions", response_model=JobPositionAdmin, status_code=201)
async def create_job_position(
    payload: JobPositionCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> JobPositionAdmin:
    code = _normalize_position_code(payload.position_code)
    exists = await session.scalar(select(JobPosition).where(JobPosition.position_code == code))
    if exists:
        raise HTTPException(409, "position_code already exists")
    row = JobPosition(
        position_code=code,
        name_th=payload.name_th.strip(),
        description=payload.description,
        sort_order=payload.sort_order,
        is_active=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return JobPositionAdmin(
        position_id=row.position_id,
        position_code=row.position_code,
        name_th=row.name_th,
        description=row.description,
        is_active=row.is_active,
        sort_order=row.sort_order,
        document_count=0,
        user_count=0,
    )


@router.patch("/job-positions/{position_id}", response_model=JobPositionAdmin)
async def update_job_position(
    position_id: uuid.UUID,
    payload: JobPositionUpdate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> JobPositionAdmin:
    row = await session.get(JobPosition, position_id)
    if row is None:
        raise HTTPException(404, "position not found")
    if payload.name_th is not None:
        row.name_th = payload.name_th.strip()
    if payload.description is not None:
        row.description = payload.description
    if payload.is_active is not None:
        row.is_active = payload.is_active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    await session.commit()
    await session.refresh(row)
    usage = await count_position_usage_batch(session, [row.position_id])
    doc_count, user_count = usage.get(row.position_id, (0, 0))
    return JobPositionAdmin(
        position_id=row.position_id,
        position_code=row.position_code,
        name_th=row.name_th,
        description=row.description,
        is_active=row.is_active,
        sort_order=row.sort_order,
        document_count=doc_count,
        user_count=user_count,
    )


@router.get("/job-positions/{position_id}/usage", response_model=JobPositionUsage)
async def job_position_usage(
    position_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> JobPositionUsage:
    row = await session.get(JobPosition, position_id)
    if row is None:
        raise HTTPException(404, "position not found")
    usage = await count_position_usage_batch(session, [position_id])
    doc_count, user_count = usage.get(position_id, (0, 0))
    return JobPositionUsage(
        position_id=position_id,
        document_count=doc_count,
        user_count=user_count,
    )


@router.get("/audit/export")
async def export_audit_retrieval_log(
    days: int = Query(90, ge=1, le=365),
    _p: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    from fastapi.responses import PlainTextResponse

    from spark.services.audit_retrieval_service import audit_retrieval_service

    csv_body = await audit_retrieval_service.export_csv(session, days=days)
    return PlainTextResponse(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit_retrieval_{days}d.csv"'},
    )
