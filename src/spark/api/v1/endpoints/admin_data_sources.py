"""Admin API for external Postgres data sources."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.core.database import get_session
from spark.core.security import Principal, require_role
from spark.schemas.data_sources import (
    ExternalConnectionTestRequest,
    ExternalConnectionTestResult,
    ExternalDataSourceCreate,
    ExternalDataSourceOut,
    ExternalDataSourceUpdate,
    ExternalDiscoveredTable,
    ExternalTableAllowlistUpdate,
    ExternalTableOut,
)
from spark.services import data_source_service as svc

router = APIRouter(prefix="/admin/data-sources", tags=["Admin"])


def _to_out(row) -> ExternalDataSourceOut:
    return ExternalDataSourceOut(
        source_id=row.source_id,
        name=row.name,
        description=row.description,
        factory_id=row.factory_id,
        host=row.host,
        port=row.port,
        database_name=row.database_name,
        username=row.username,
        ssl_mode=row.ssl_mode,
        scope_column=row.scope_column,
        is_enabled=row.is_enabled,
        allowed_tables=[
            ExternalTableOut(
                table_id=t.table_id,
                schema_name=t.schema_name,
                table_name=t.table_name,
                description=t.description,
                columns_meta=t.columns_meta or [],
                factory_ids=[f.factory_id for f in t.factories],
                position_ids=[p.position_id for p in t.job_positions],
            )
            for t in row.allowed_tables
        ],
    )


@router.get("", response_model=list[ExternalDataSourceOut], responses=WRITE_ERRORS)
async def list_data_sources(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> list[ExternalDataSourceOut]:
    rows = await svc.list_data_sources(session)
    return [_to_out(r) for r in rows]


@router.post("", response_model=ExternalDataSourceOut, status_code=201, responses=WRITE_ERRORS)
async def create_data_source(
    payload: ExternalDataSourceCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("admin")),
) -> ExternalDataSourceOut:
    created_by = uuid.UUID(str(principal.user_id)) if principal.user_id else None
    row = await svc.create_data_source(
        session,
        payload=payload.model_dump(),
        created_by=created_by,
    )
    await session.commit()
    row = await svc.get_data_source(session, row.source_id)
    assert row is not None
    return _to_out(row)


@router.post("/test", response_model=ExternalConnectionTestResult, responses=WRITE_ERRORS)
async def test_connection_before_create(
    payload: ExternalConnectionTestRequest,
    _: Principal = Depends(require_role("admin")),
) -> ExternalConnectionTestResult:
    """Test raw connection params from the create-form, before anything is saved."""
    ok, message = await svc.test_connection_params(
        host=payload.host,
        port=payload.port,
        database_name=payload.database_name,
        username=payload.username,
        password=payload.password,
        ssl_mode=payload.ssl_mode,
    )
    return ExternalConnectionTestResult(ok=ok, message=message)


@router.get("/{source_id}", response_model=ExternalDataSourceOut, responses=WRITE_ERRORS)
async def get_data_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> ExternalDataSourceOut:
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    return _to_out(row)


@router.patch("/{source_id}", response_model=ExternalDataSourceOut, responses=WRITE_ERRORS)
async def update_data_source(
    source_id: uuid.UUID,
    payload: ExternalDataSourceUpdate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> ExternalDataSourceOut:
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    data = payload.model_dump(exclude_unset=True)
    row = await svc.update_data_source(session, row, payload=data)
    await session.commit()
    row = await svc.get_data_source(session, source_id)
    assert row is not None
    return _to_out(row)


@router.delete("/{source_id}", status_code=204, responses={404: {"description": "Not found"}, **WRITE_ERRORS})
async def delete_data_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
):
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    await svc.delete_data_source(session, row)
    await session.commit()


@router.post("/{source_id}/test", response_model=ExternalConnectionTestResult, responses=WRITE_ERRORS)
async def test_data_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> ExternalConnectionTestResult:
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    ok, message = await svc.test_data_source(row)
    return ExternalConnectionTestResult(ok=ok, message=message)


@router.get("/{source_id}/discover", response_model=list[ExternalDiscoveredTable], responses=WRITE_ERRORS)
async def discover_tables(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> list[ExternalDiscoveredTable]:
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    try:
        discovered = await svc.discover_data_source_tables(row)
    except Exception as exc:
        raise HTTPException(502, f"discover failed: {exc}") from exc
    return [ExternalDiscoveredTable(**item) for item in discovered]


@router.put("/{source_id}/tables", response_model=ExternalDataSourceOut, responses=WRITE_ERRORS)
async def set_allowed_tables(
    source_id: uuid.UUID,
    payload: ExternalTableAllowlistUpdate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("admin")),
) -> ExternalDataSourceOut:
    row = await svc.get_data_source(session, source_id)
    if row is None:
        raise HTTPException(404, "data source not found")
    tables = [t.model_dump() for t in payload.tables]
    row = await svc.replace_allowed_tables(session, row, tables)
    await session.commit()
    row = await svc.get_data_source(session, source_id)
    assert row is not None
    return _to_out(row)
