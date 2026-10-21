"""Extend vector reconcile service for Phase 5 auto-heal."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import ingest_vector_drift_detected_total, vector_drift_detected_total
from spark.core.qdrant_strategy import collection_for_document
from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.index.qdrant_writer import QdrantWriter

log = get_logger(__name__)

_LOCK_PREFIX = "spark:vector_reconcile:lock:"
_RESULT_PREFIX = "spark:vector_reconcile:last:"
_LOCK_TTL_SEC = 3600
_RESULT_TTL_SEC = 604_800


@dataclass
class ReconcileMismatch:
    doc_id: str
    factory_id: str | None
    active_generation: int
    pg_count: int
    qdrant_count: int
    collection: str
    is_ghost: bool = False
    fixed: bool = False
    reupserted: bool = False


@dataclass
class ReconcileResult:
    factory_id: str | None
    auto_fix: bool
    docs_scanned: int = 0
    mismatch_count: int = 0
    fixed_count: int = 0
    reupserted_count: int = 0
    drift_rate: float = 0.0
    drift_alert: bool = False
    mismatches: list[ReconcileMismatch] = field(default_factory=list)
    completed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mismatches"] = [asdict(item) for item in self.mismatches[:50]]
        return payload


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _lock_key(factory_id: str | None) -> str:
    return f"{_LOCK_PREFIX}{factory_id or 'global'}"


def _result_key(factory_id: str | None) -> str:
    return f"{_RESULT_PREFIX}{factory_id or 'global'}"


def acquire_reconcile_lock(factory_id: str | None, *, ttl_sec: int = _LOCK_TTL_SEC) -> bool:
    try:
        return bool(
            _redis_client().set(_lock_key(factory_id), "1", nx=True, ex=max(60, ttl_sec))
        )
    except Exception as exc:
        log.warning("vector_reconcile_lock_failed", error=str(exc)[:120])
        return True


def release_reconcile_lock(factory_id: str | None) -> None:
    try:
        _redis_client().delete(_lock_key(factory_id))
    except Exception as exc:
        log.warning("vector_reconcile_unlock_failed", error=str(exc)[:120])


def save_last_reconcile_result(result: ReconcileResult) -> None:
    try:
        client = _redis_client()
        payload = json.dumps(result.to_dict())
        client.set(_result_key(result.factory_id), payload, ex=_RESULT_TTL_SEC)
        client.set(_result_key(None), payload, ex=_RESULT_TTL_SEC)
    except Exception as exc:
        log.warning("vector_reconcile_result_store_failed", error=str(exc)[:120])


def get_last_reconcile_summary(factory_id: str | None = None) -> dict[str, Any] | None:
    try:
        raw = _redis_client().get(_result_key(factory_id))
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        log.warning("vector_reconcile_result_read_failed", error=str(exc)[:120])
        return None


def _drift_threshold() -> float:
    return max(0.0, float(getattr(settings, "vector_drift_threshold_pct", 0.02)))


class VectorReconcileService:
    async def reconcile(
        self,
        session: AsyncSession,
        *,
        factory_id: str | None = None,
        auto_fix: bool = False,
    ) -> ReconcileResult:
        router = QdrantWriter()
        result = ReconcileResult(factory_id=factory_id, auto_fix=auto_fix)

        stmt = select(Document).where(
            Document.chunks_count > 0,
            Document.ingest_status != "failed",
            Document.retrieval_enabled.is_(True),
        )
        if factory_id:
            stmt = stmt.where(Document.factory_id == factory_id)
        docs = (await session.execute(stmt)).scalars().all()
        result.docs_scanned = len(docs)

        for doc in docs:
            pg_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(
                        DocumentChunk.doc_id == doc.doc_id,
                        DocumentChunk.ingest_generation == doc.active_ingest_generation,
                    )
                )
                or 0
            )
            collection = collection_for_document(doc.document_type, doc.factory_id, doc.document_category)
            qdrant_count = await router.count_by_doc(
                doc.doc_id,
                collection=collection,
                generation=doc.active_ingest_generation,
            )
            if pg_count == qdrant_count:
                continue

            is_ghost = qdrant_count > pg_count
            mismatch = ReconcileMismatch(
                doc_id=str(doc.doc_id),
                factory_id=doc.factory_id,
                active_generation=int(doc.active_ingest_generation),
                pg_count=pg_count,
                qdrant_count=qdrant_count,
                collection=collection,
                is_ghost=is_ghost,
            )
            result.mismatch_count += 1
            log.warning(
                "ingest_reconcile_mismatch",
                doc_id=mismatch.doc_id,
                factory_id=mismatch.factory_id,
                active_generation=mismatch.active_generation,
                pg_count=pg_count,
                qdrant_count=qdrant_count,
                is_ghost=is_ghost,
            )

            if auto_fix:
                if is_ghost:
                    await router.delete_by_doc_except_generation(
                        doc.doc_id,
                        keep_generation=doc.active_ingest_generation,
                        collection=collection,
                    )
                    mismatch.fixed = True
                    result.fixed_count += 1
                elif qdrant_count < pg_count:
                    document_context = {
                        "factory_id": doc.factory_id,
                        "machine_id": doc.machine_id,
                        "document_category": doc.document_category,
                        "document_type": doc.document_type,
                        "language": doc.language,
                        "revision": doc.revision,
                        "source_file": doc.source_file,
                        "title": doc.title,
                    }
                    await router.reupsert_from_pg_mirror(
                        session,
                        doc.doc_id,
                        generation=doc.active_ingest_generation,
                        collection=collection,
                        document_context=document_context,
                    )
                    mismatch.reupserted = True
                    result.reupserted_count += 1
                log.info(
                    "ingest_reconcile_fixed",
                    doc_id=mismatch.doc_id,
                    reupserted=mismatch.reupserted,
                )

            result.mismatches.append(mismatch)

        if result.docs_scanned:
            result.drift_rate = result.mismatch_count / result.docs_scanned
        result.drift_alert = result.drift_rate > _drift_threshold()

        if result.drift_alert:
            vector_drift_detected_total.labels(factory_id or "global").inc(result.mismatch_count)
            ingest_vector_drift_detected_total.labels(factory_id or "global").inc(
                result.mismatch_count
            )
            await self._notify_drift(session, result)

        save_last_reconcile_result(result)
        return result

    async def _notify_drift(self, session: AsyncSession, result: ReconcileResult) -> None:
        from spark.services.notification_dispatch_service import notification_dispatch_service

        factories = {m.factory_id for m in result.mismatches if m.factory_id}
        if result.factory_id:
            factories.add(result.factory_id)
        if not factories:
            factories.add("unknown")

        subject = "Vector drift detected — PG/Qdrant mirror mismatch"
        body = (
            f"Reconcile found {result.mismatch_count} document(s) with generation drift "
            f"({result.drift_rate:.1%} of {result.docs_scanned} scanned). "
            f"auto_fix={'on' if result.auto_fix else 'off'}."
        )
        for fid in sorted(factories):
            if not fid or fid == "unknown":
                continue
            try:
                await notification_dispatch_service.notify_factory(
                    session,
                    factory_id=fid,
                    event_type="vector_drift",
                    subject=subject,
                    body=body,
                    context=result.to_dict(),
                )
            except Exception as exc:
                log.warning(
                    "vector_drift_notify_failed",
                    factory_id=fid,
                    error=str(exc)[:120],
                )


vector_reconcile_service = VectorReconcileService()


async def run_vector_reconcile(
    *,
    factory_id: str | None = None,
    auto_fix: bool = False,
) -> ReconcileResult:
    from spark.core.database import AsyncSessionLocal

    if not acquire_reconcile_lock(factory_id):
        log.info("vector_reconcile_skipped_locked", factory_id=factory_id)
        cached = get_last_reconcile_summary(factory_id)
        if cached:
            return ReconcileResult(
                factory_id=factory_id,
                auto_fix=auto_fix,
                docs_scanned=int(cached.get("docs_scanned") or 0),
                mismatch_count=int(cached.get("mismatch_count") or 0),
                fixed_count=int(cached.get("fixed_count") or 0),
                reupserted_count=int(cached.get("reupserted_count") or 0),
                drift_rate=float(cached.get("drift_rate") or 0.0),
                drift_alert=bool(cached.get("drift_alert")),
            )
        return ReconcileResult(factory_id=factory_id, auto_fix=auto_fix)

    try:
        async with AsyncSessionLocal() as session:
            result = await vector_reconcile_service.reconcile(
                session,
                factory_id=factory_id,
                auto_fix=auto_fix,
            )
            await session.commit()
            return result
    finally:
        release_reconcile_lock(factory_id)
