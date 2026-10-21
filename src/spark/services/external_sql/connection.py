"""External Postgres connection + introspection (read-only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.secret_box import decrypt_secret
from spark.db.models.data_sources import ExternalDataSource

log = get_logger(__name__)

_engine_cache: dict[uuid.UUID, AsyncEngine] = {}


@dataclass(frozen=True)
class ExternalConnectionConfig:
    source_id: uuid.UUID
    host: str
    port: int
    database_name: str
    username: str
    password: str
    ssl_mode: str


def connection_config_from_model(source: ExternalDataSource) -> ExternalConnectionConfig:
    return ExternalConnectionConfig(
        source_id=source.source_id,
        host=source.host,
        port=int(source.port),
        database_name=source.database_name,
        username=source.username,
        password=decrypt_secret(source.password_encrypted),
        ssl_mode=source.ssl_mode or "prefer",
    )


def _database_url(cfg: ExternalConnectionConfig) -> str:
    user = quote_plus(cfg.username)
    password = quote_plus(cfg.password)
    base = f"postgresql+asyncpg://{user}:{password}@{cfg.host}:{cfg.port}/{cfg.database_name}"
    if cfg.ssl_mode in {"require", "verify-ca", "verify-full"}:
        return f"{base}?ssl=true"
    return base


def get_external_engine(cfg: ExternalConnectionConfig) -> AsyncEngine:
    cached = _engine_cache.get(cfg.source_id)
    if cached is not None:
        return cached
    engine = create_async_engine(
        _database_url(cfg),
        echo=False,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
    )
    _engine_cache[cfg.source_id] = engine
    return engine


async def dispose_external_engine(source_id: uuid.UUID) -> None:
    engine = _engine_cache.pop(source_id, None)
    if engine is not None:
        await engine.dispose()


async def test_connection(cfg: ExternalConnectionConfig) -> tuple[bool, str]:
    engine = get_external_engine(cfg)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            ro = await conn.execute(text("SHOW transaction_read_only"))
            _ = ro.scalar()
        return True, "connection ok"
    except Exception as exc:
        return False, str(exc)[:500]


async def test_ad_hoc_connection(
    *, host: str, port: int, database_name: str, username: str, password: str, ssl_mode: str
) -> tuple[bool, str]:
    """Test raw connection params before a data source row exists (admin create-form)."""
    cfg = ExternalConnectionConfig(
        source_id=uuid.uuid4(),
        host=host,
        port=port,
        database_name=database_name,
        username=username,
        password=password,
        ssl_mode=ssl_mode,
    )
    try:
        return await test_connection(cfg)
    finally:
        await dispose_external_engine(cfg.source_id)


async def execute_external_select(
    cfg: ExternalConnectionConfig,
    sql: str,
    *,
    timeout_ms: int | None = None,
) -> list[dict[str, Any]]:
    engine = get_external_engine(cfg)
    timeout = timeout_ms or settings.sql_statement_timeout_ms
    ms = str(max(1000, min(int(timeout), 30000)))
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('statement_timeout', :val, true)"), {"val": ms})
        await conn.execute(text("SET LOCAL transaction_read_only = ON"))
        result = await conn.execute(text(sql))
        return [dict(row) for row in result.mappings().all()]


async def discover_tables(cfg: ExternalConnectionConfig) -> list[dict[str, Any]]:
    sql = """
        SELECT table_schema, table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND table_schema NOT LIKE 'pg_%'
        ORDER BY table_schema, table_name, ordinal_position
    """
    engine = get_external_engine(cfg)
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        rows = [dict(r) for r in result.mappings().all()]

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row["table_schema"], row["table_name"])
        grouped.setdefault(key, []).append(
            {
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"],
            }
        )
    return [
        {
            "schema_name": schema,
            "table_name": table,
            "columns": cols,
        }
        for (schema, table), cols in sorted(grouped.items())
    ]
