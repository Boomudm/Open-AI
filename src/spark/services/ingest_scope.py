from __future__ import annotations

import json
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.job_positions import DocumentJobPosition, JobPosition
from spark.db.models.org import Machine


async def resolve_ingest_factory_id(
    session: AsyncSession,
    *,
    factory_id: str | None,
    machine_id: str | None,
) -> str:
    """Resolve factory_id for ingest; raise 422 on invalid input."""
    resolved = (factory_id or "").strip() or None
    machine_key = (machine_id or "").strip() or None

    if machine_key:
        machine = await session.get(Machine, machine_key)
        if machine is None:
            raise HTTPException(422, "unknown machine_id")
        if resolved and machine.factory_id != resolved:
            raise HTTPException(422, "machine does not belong to factory")
        if not resolved:
            resolved = machine.factory_id

    if not resolved:
        raise HTTPException(422, "factory_id required")

    return resolved


def parse_visible_position_ids(raw: str | None) -> list[uuid.UUID]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "visible_position_ids must be a JSON array") from exc
    if not isinstance(parsed, list):
        raise HTTPException(422, "visible_position_ids must be a JSON array")
    out: list[uuid.UUID] = []
    for item in parsed:
        try:
            out.append(uuid.UUID(str(item)))
        except ValueError as exc:
            raise HTTPException(422, f"invalid position id: {item}") from exc
    return out


async def validate_active_position_ids(
    session: AsyncSession,
    position_ids: list[uuid.UUID],
) -> None:
    if not position_ids:
        return
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


async def set_document_job_positions(
    session: AsyncSession,
    doc_id: uuid.UUID,
    position_ids: list[uuid.UUID],
) -> None:
    from spark.db.models.docs import Document
    from spark.services.acl.mutation_hooks import on_document_positions_changed

    existing = (
        await session.execute(
            select(DocumentJobPosition).where(DocumentJobPosition.doc_id == doc_id)
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    for position_id in position_ids:
        session.add(DocumentJobPosition(doc_id=doc_id, position_id=position_id))

    doc = await session.get(Document, doc_id)
    await on_document_positions_changed(
        session,
        factory_id=doc.factory_id if doc else None,
        doc_id=doc_id,
        position_ids=position_ids,
    )
