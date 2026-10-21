"""CRUD + resolution for external Postgres data sources."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.core.secret_box import encrypt_secret
from spark.db.models.data_sources import ExternalDataSource, ExternalDataSourceTable
from spark.db.models.job_positions import JobPosition
from spark.db.models.org import Factory
from spark.services.external_sql.connection import (
    connection_config_from_model,
    discover_tables,
    dispose_external_engine,
    test_ad_hoc_connection,
    test_connection,
)


@dataclass(frozen=True)
class ExternalSourceBundle:
    source: ExternalDataSource
    allowed_table_names: frozenset[str]
    visible_tables: list[ExternalDataSourceTable]

    @property
    def has_tables(self) -> bool:
        return bool(self.allowed_table_names)


async def list_data_sources(session: AsyncSession) -> list[ExternalDataSource]:
    rows = (
        await session.execute(
            select(ExternalDataSource)
            .options(selectinload(ExternalDataSource.allowed_tables))
            .order_by(ExternalDataSource.name)
        )
    ).scalars().all()
    return list(rows)


async def get_data_source(session: AsyncSession, source_id: uuid.UUID) -> ExternalDataSource | None:
    return (
        await session.execute(
            select(ExternalDataSource)
            .where(ExternalDataSource.source_id == source_id)
            .options(selectinload(ExternalDataSource.allowed_tables))
        )
    ).scalar_one_or_none()


async def create_data_source(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    created_by: uuid.UUID | None,
) -> ExternalDataSource:
    row = ExternalDataSource(
        name=payload["name"],
        description=payload.get("description"),
        factory_id=payload.get("factory_id"),
        host=payload["host"],
        port=int(payload.get("port") or 5432),
        database_name=payload["database_name"],
        username=payload["username"],
        password_encrypted=encrypt_secret(payload["password"]),
        ssl_mode=payload.get("ssl_mode") or "prefer",
        scope_column=(payload.get("scope_column") or None),
        is_enabled=bool(payload.get("is_enabled", False)),
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row, attribute_names=["allowed_tables"])
    return row


async def update_data_source(
    session: AsyncSession,
    row: ExternalDataSource,
    *,
    payload: dict[str, Any],
) -> ExternalDataSource:
    for field in ("name", "description", "factory_id", "host", "port", "database_name", "username", "ssl_mode", "scope_column", "is_enabled"):
        if field in payload:
            setattr(row, field, payload[field])
    if "password" in payload and payload["password"]:
        row.password_encrypted = encrypt_secret(payload["password"])
        await dispose_external_engine(row.source_id)
    await session.flush()
    return row


async def delete_data_source(session: AsyncSession, row: ExternalDataSource) -> None:
    await dispose_external_engine(row.source_id)
    await session.delete(row)


async def replace_allowed_tables(
    session: AsyncSession,
    source: ExternalDataSource,
    tables: list[dict[str, Any]],
) -> ExternalDataSource:
    source.allowed_tables.clear()
    await session.flush()

    all_factory_ids = {fid for item in tables for fid in (item.get("factory_ids") or [])}
    all_position_ids = {pid for item in tables for pid in (item.get("position_ids") or [])}
    factories_by_id = {}
    positions_by_id = {}
    if all_factory_ids:
        rows = (
            await session.execute(select(Factory).where(Factory.factory_id.in_(all_factory_ids)))
        ).scalars().all()
        factories_by_id = {f.factory_id: f for f in rows}
    if all_position_ids:
        rows = (
            await session.execute(select(JobPosition).where(JobPosition.position_id.in_(all_position_ids)))
        ).scalars().all()
        positions_by_id = {p.position_id: p for p in rows}

    for item in tables:
        table_row = ExternalDataSourceTable(
            schema_name=item.get("schema_name") or "public",
            table_name=item["table_name"],
            description=item.get("description"),
            columns_meta=item.get("columns_meta") or [],
        )
        table_row.factories = [
            factories_by_id[fid] for fid in (item.get("factory_ids") or []) if fid in factories_by_id
        ]
        table_row.job_positions = [
            positions_by_id[pid] for pid in (item.get("position_ids") or []) if pid in positions_by_id
        ]
        source.allowed_tables.append(table_row)
    await session.flush()
    await session.refresh(source, attribute_names=["allowed_tables"])
    return source


async def test_data_source(row: ExternalDataSource) -> tuple[bool, str]:
    cfg = connection_config_from_model(row)
    return await test_connection(cfg)


async def test_connection_params(
    *, host: str, port: int, database_name: str, username: str, password: str, ssl_mode: str
) -> tuple[bool, str]:
    """Test raw connection params from the admin create-form, before anything is saved."""
    return await test_ad_hoc_connection(
        host=host,
        port=port,
        database_name=database_name,
        username=username,
        password=password,
        ssl_mode=ssl_mode,
    )


async def discover_data_source_tables(row: ExternalDataSource) -> list[dict[str, Any]]:
    cfg = connection_config_from_model(row)
    return await discover_tables(cfg)


async def resolve_external_source_for_factory(
    session: AsyncSession,
    factory_id: str | None,
    *,
    job_position_ids: list[str] | None = None,
) -> ExternalSourceBundle | None:
    if not factory_id:
        return None
    stmt = (
        select(ExternalDataSource)
        .where(
            ExternalDataSource.is_enabled.is_(True),
            or_(
                ExternalDataSource.factory_id == factory_id,
                ExternalDataSource.factory_id.is_(None),
            ),
        )
        .options(selectinload(ExternalDataSource.allowed_tables))
        .order_by(ExternalDataSource.factory_id.desc().nullslast())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None or not row.allowed_tables:
        return None

    position_ids = {str(p) for p in (job_position_ids or [])}
    visible_tables = [
        t
        for t in row.allowed_tables
        if (not t.factories or any(f.factory_id == factory_id for f in t.factories))
        and (not t.job_positions or any(str(p.position_id) in position_ids for p in t.job_positions))
    ]
    if not visible_tables:
        return None
    names = frozenset(t.table_name.casefold() for t in visible_tables)
    return ExternalSourceBundle(source=row, allowed_table_names=names, visible_tables=visible_tables)


def build_schema_context(
    source: ExternalDataSource, tables: list[ExternalDataSourceTable] | None = None
) -> str:
    lines = [
        "ตารางที่อนุญาต (external Postgres):",
        "กติกา: SELECT เท่านั้น, PostgreSQL syntax, ตอบเป็น SQL ตัวเดียว",
    ]
    if source.scope_column and source.factory_id:
        lines.append(
            f"- ต้อง filter {source.scope_column} = '{source.factory_id}' ในทุก query"
        )
    for table in tables if tables is not None else source.allowed_tables:
        qualified = f"{table.schema_name}.{table.table_name}"
        desc = table.description or ""
        cols = table.columns_meta or []
        if cols:
            col_txt = ", ".join(
                f"{c.get('column_name')} ({c.get('data_type')})" for c in cols[:40]
            )
            lines.append(f"- {qualified}: {desc} columns: {col_txt}")
        else:
            lines.append(f"- {qualified}: {desc}")
    return "\n".join(lines)
