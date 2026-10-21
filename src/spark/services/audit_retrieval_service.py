"""Append-only retrieval audit log and compliance export (Phase 14)."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.audit.worm_sink import verify_event_chain
from spark.db.models.audit import AuditRetrievalLog
from spark.db.models.worm_audit import AuditEventImmutable


class AuditRetrievalService:
    async def record(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None,
        factory_id: str | None,
        question: str,
        route: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> None:
        for src in sources or [][:10]:
            raw_doc = src.get("doc_id")
            doc_id = uuid.UUID(str(raw_doc)) if raw_doc else None
            page = src.get("page")
            db.add(
                AuditRetrievalLog(
                    user_id=user_id,
                    factory_id=factory_id,
                    question=question[:2000],
                    doc_id=doc_id,
                    page=int(page) if page is not None else None,
                    route=route,
                )
            )
        if not sources:
            db.add(
                AuditRetrievalLog(
                    user_id=user_id,
                    factory_id=factory_id,
                    question=question[:2000],
                    route=route,
                )
            )
        await db.flush()

    async def export_csv(self, db: AsyncSession, *, days: int = 90, limit: int = 50_000) -> str:
        since = datetime.now(tz=UTC) - timedelta(days=max(1, days))
        rows = (
            await db.execute(
                select(AuditRetrievalLog)
                .where(AuditRetrievalLog.created_at >= since)
                .order_by(AuditRetrievalLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["created_at", "factory_id", "user_id", "route", "question", "doc_id", "page"])
        for row in rows:
            writer.writerow(
                [
                    row.created_at.isoformat() if row.created_at else "",
                    row.factory_id or "",
                    str(row.user_id) if row.user_id else "",
                    row.route,
                    row.question,
                    str(row.doc_id) if row.doc_id else "",
                    row.page if row.page is not None else "",
                ]
            )
        return buf.getvalue()

    async def export_compliance_bundle(
        self,
        db: AsyncSession,
        *,
        factory_id: str | None,
        days: int = 90,
        limit: int = 10_000,
    ) -> dict[str, Any]:
        since = datetime.now(tz=UTC) - timedelta(days=max(1, days))

        retrieval_q = (
            select(AuditRetrievalLog)
            .where(AuditRetrievalLog.created_at >= since)
            .order_by(AuditRetrievalLog.created_at.desc())
            .limit(limit)
        )
        worm_q = (
            select(AuditEventImmutable)
            .where(AuditEventImmutable.occurred_at >= since)
            .order_by(AuditEventImmutable.occurred_at.asc())
            .limit(limit)
        )
        if factory_id:
            retrieval_q = retrieval_q.where(AuditRetrievalLog.factory_id == factory_id)
            worm_q = worm_q.where(AuditEventImmutable.factory_id == factory_id)

        retrieval_rows = (await db.execute(retrieval_q)).scalars().all()

        worm_rows: list[AuditEventImmutable] = []
        try:
            worm_rows = (await db.execute(worm_q)).scalars().all()
        except Exception:
            worm_rows = []

        chain_valid, _broken = verify_event_chain(list(worm_rows))

        return {
            "factory_id": factory_id,
            "days": days,
            "retrieval_rows": len(retrieval_rows),
            "worm_events": len(worm_rows),
            "chain_valid": chain_valid,
            "retrieval_log": [
                {
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "factory_id": row.factory_id,
                    "user_id": str(row.user_id) if row.user_id else None,
                    "route": row.route,
                    "question": row.question,
                    "doc_id": str(row.doc_id) if row.doc_id else None,
                    "page": row.page,
                }
                for row in retrieval_rows
            ],
            "worm_audit": [
                {
                    "event_id": str(row.event_id),
                    "event_type": row.event_type,
                    "occurred_at": row.occurred_at.isoformat(),
                    "actor_id": row.actor_id,
                    "factory_id": row.factory_id,
                    "payload": dict(row.payload or {}),
                    "prev_hash": row.prev_hash,
                    "event_hash": row.event_hash,
                }
                for row in worm_rows
            ],
        }


audit_retrieval_service = AuditRetrievalService()
