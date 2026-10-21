"""Batch admin user list assembly (app-layer Phase 4)."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.job_positions import DocumentJobPosition, JobPosition, UserJobPosition
from spark.db.models.org import Role, User, UserFactoryAccess, UserRole
from spark.schemas.job_positions import AdminUserBrief, FactoryAccessEntry, JobPositionAdmin


async def load_admin_users_batch(
    session: AsyncSession,
    users: list[User],
) -> list[AdminUserBrief]:
    if not users:
        return []

    user_ids = [user.user_id for user in users]
    roles_by_user: dict[uuid.UUID, list[str]] = defaultdict(list)
    access_by_user: dict[uuid.UUID, list[FactoryAccessEntry]] = defaultdict(list)
    positions_by_user: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)

    role_rows = (
        await session.execute(
            select(UserRole.user_id, Role.role_code)
            .join(Role, Role.role_id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
        )
    ).all()
    for user_id, role_code in role_rows:
        roles_by_user[user_id].append(role_code)

    access_rows = (
        await session.execute(
            select(
                UserFactoryAccess.user_id,
                UserFactoryAccess.factory_id,
                UserFactoryAccess.access_level,
            ).where(UserFactoryAccess.user_id.in_(user_ids))
        )
    ).all()
    for user_id, factory_id, access_level in access_rows:
        access_by_user[user_id].append(
            FactoryAccessEntry(factory_id=factory_id, access_level=access_level)
        )

    position_rows = (
        await session.execute(
            select(UserJobPosition.user_id, UserJobPosition.position_id).where(
                UserJobPosition.user_id.in_(user_ids)
            )
        )
    ).all()
    for user_id, position_id in position_rows:
        positions_by_user[user_id].append(position_id)

    return [
        AdminUserBrief(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            email=user.email,
            is_active=user.is_active,
            roles=list(roles_by_user.get(user.user_id, [])),
            factory_access=list(access_by_user.get(user.user_id, [])),
            job_position_ids=list(positions_by_user.get(user.user_id, [])),
            token_version=user.token_version,
            is_super_admin=bool(user.is_super_admin),
        )
        for user in users
    ]


async def count_position_usage_batch(
    session: AsyncSession,
    position_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    if not position_ids:
        return {}

    doc_rows = (
        await session.execute(
            select(
                DocumentJobPosition.position_id,
                func.count(),
            )
            .select_from(DocumentJobPosition)
            .where(DocumentJobPosition.position_id.in_(position_ids))
            .group_by(DocumentJobPosition.position_id)
        )
    ).all()
    user_rows = (
        await session.execute(
            select(
                UserJobPosition.position_id,
                func.count(),
            )
            .select_from(UserJobPosition)
            .where(UserJobPosition.position_id.in_(position_ids))
            .group_by(UserJobPosition.position_id)
        )
    ).all()

    doc_map = {pid: int(count) for pid, count in doc_rows}
    user_map = {pid: int(count) for pid, count in user_rows}
    return {
        pid: (doc_map.get(pid, 0), user_map.get(pid, 0))
        for pid in position_ids
    }


async def load_job_positions_admin_batch(
    session: AsyncSession,
    rows: list[JobPosition],
) -> list[JobPositionAdmin]:
    usage = await count_position_usage_batch(session, [row.position_id for row in rows])
    return [
        JobPositionAdmin(
            position_id=row.position_id,
            position_code=row.position_code,
            name_th=row.name_th,
            description=row.description,
            is_active=row.is_active,
            sort_order=row.sort_order,
            document_count=usage.get(row.position_id, (0, 0))[0],
            user_count=usage.get(row.position_id, (0, 0))[1],
        )
        for row in rows
    ]
