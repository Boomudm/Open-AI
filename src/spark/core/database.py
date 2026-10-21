from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from spark.core.config import settings


class Base(DeclarativeBase):
    pass


_testing = bool(os.getenv("SPARK_TESTING"))
# Celery tasks each run their own asyncio.run() (their own throwaway event loop).
# A persistent pool hands out connections checked in by a *previous* task, which
# are bound to that task's now-closed loop — the checkout raises 'RuntimeError:
# Event loop is closed', and by the time anything notices, there's no live loop
# left to close the stale connection either. NullPool sidesteps this entirely:
# every checkout is a fresh connection, opened and closed within one task's own
# loop. See spark.workers.celery_app, which sets this flag before importing
# anything that could import this module.
_no_pool = _testing or bool(os.getenv("SPARK_CELERY_WORKER"))

_engine_kwargs: dict = {
    "echo": False,
    "pool_pre_ping": not _no_pool,
}
if not _testing:
    _engine_kwargs["connect_args"] = {"command_timeout": 30}
if _no_pool:
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["pool_size"] = settings.db_pool_size
    _engine_kwargs["max_overflow"] = settings.db_max_overflow
    _engine_kwargs["pool_recycle"] = settings.db_pool_recycle

engine = create_async_engine(settings.database_url, **_engine_kwargs)

_stream_engine_kwargs = dict(_engine_kwargs)
if not _testing:
    _stream_engine_kwargs["connect_args"] = {"command_timeout": 60}
if not _no_pool:
    _stream_engine_kwargs["pool_size"] = settings.db_stream_pool_size
    _stream_engine_kwargs["max_overflow"] = max(2, settings.db_stream_pool_size)

stream_engine = create_async_engine(settings.database_url, **_stream_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

StreamSessionLocal = async_sessionmaker(
    stream_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def db_pool_snapshot() -> dict[str, int]:
    """Best-effort SQLAlchemy pool counters for /readyz."""
    if _testing:
        return {"size": 0, "checked_in": 0, "checked_out": 0, "overflow": 0}
    pool = engine.pool
    return {
        "size": int(pool.size()),
        "checked_in": int(pool.checkedin()),
        "checked_out": int(pool.checkedout()),
        "overflow": int(pool.overflow()),
    }


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
