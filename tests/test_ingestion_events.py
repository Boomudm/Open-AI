"""Ingestion event log integration (Phase 3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from spark.core.database import AsyncSessionLocal
from spark.db.models.ingestion_events import IngestionEvent
from spark.services.ingest_events import append_ingestion_event


@pytest.mark.asyncio
async def test_append_ingestion_event_persists() -> None:
    job_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        from spark.db.models.docs import Document
        from spark.db.models.ingestion import IngestionJob

        session.add(
            Document(
                doc_id=doc_id,
                document_category="knowledge",
                document_type="machine_manual",
                source_file="test.pdf",
                ingest_status="pending",
            )
        )
        session.add(
            IngestionJob(
                job_id=job_id,
                doc_id=doc_id,
                document_type="machine_manual",
                status="running",
            )
        )
        await append_ingestion_event(
            session,
            job_id=job_id,
            stage="parse",
            code="parse_complete",
            detail={"rows_total": 3},
        )
        await session.commit()
        rows = (
            await session.execute(select(IngestionEvent).where(IngestionEvent.job_id == job_id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].stage == "parse"
        assert rows[0].code == "parse_complete"
