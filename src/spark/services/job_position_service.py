from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.job_positions import JobPosition, UserJobPosition
from spark.db.models.org import User


async def set_user_job_positions(
    session: AsyncSession,
    user: User,
    position_ids: list[uuid.UUID],
) -> None:
    if position_ids:
        rows = (
            await session.execute(
                select(JobPosition.position_id).where(
                    JobPosition.position_id.in_(position_ids),
                    JobPosition.is_active.is_(True),
                )
            )
        ).scalars().all()
        found = set(rows)
        missing = [str(pid) for pid in position_ids if pid not in found]
        if missing:
            raise HTTPException(422, f"unknown or inactive position ids: {', '.join(missing)}")
    await session.execute(delete(UserJobPosition).where(UserJobPosition.user_id == user.user_id))
    for position_id in position_ids:
        session.add(UserJobPosition(user_id=user.user_id, position_id=position_id))
    from spark.services.acl.mutation_hooks import on_user_positions_changed

    await on_user_positions_changed(session, user_id=user.user_id)
