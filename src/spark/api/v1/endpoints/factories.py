from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.database import get_session
from spark.core.security import Principal, accessible_factory_ids, get_principal
from spark.db.models.org import Factory
from spark.schemas.factories import FactoryBrief
from spark.services.master_data_service import MasterDataService

router = APIRouter(tags=["Factories"])

master_data_service = MasterDataService()


@router.get("/factories", response_model=list[FactoryBrief])
async def list_factories(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[FactoryBrief]:
    p: Principal = get_principal(request)
    allowed = accessible_factory_ids(p)
    if allowed is None:
        rows = await master_data_service.list_factories(session)
    elif not allowed:
        return []
    else:
        rows = (
            await session.execute(
                select(Factory)
                .where(Factory.factory_id.in_(allowed))
                .order_by(Factory.factory_id)
            )
        ).scalars().all()
    return [
        FactoryBrief(factory_id=row.factory_id, factory_name=row.factory_name) for row in rows
    ]
