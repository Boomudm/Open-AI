from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.database import get_session
from spark.core.security import get_principal
from spark.db.models.job_positions import JobPosition
from spark.schemas.job_positions import JobPositionBrief

router = APIRouter(tags=["Job Positions"])


@router.get("/job-positions", response_model=list[JobPositionBrief])
async def list_active_job_positions(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[JobPositionBrief]:
    _ = get_principal(request)
    rows = (
        await session.execute(
            select(JobPosition)
            .where(JobPosition.is_active.is_(True))
            .order_by(JobPosition.sort_order, JobPosition.name_th)
        )
    ).scalars().all()
    return [
        JobPositionBrief(
            position_id=row.position_id,
            position_code=row.position_code,
            name_th=row.name_th,
            description=row.description,
        )
        for row in rows
    ]
