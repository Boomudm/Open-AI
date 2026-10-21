"""Append-only ingest job events for SSE and ops dashboards."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.ingestion_events import IngestionEvent


async def append_ingestion_event(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    stage: str,
    code: str,
    level: str = "info",
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        IngestionEvent(
            job_id=job_id,
            stage=stage,
            level=level,
            code=code,
            detail_json=detail,
        )
    )
