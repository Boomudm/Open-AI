"""Re-scan corpus when ingest content policy version bumps (Phase 11)."""

from __future__ import annotations

import asyncio
from typing import Any

import redis
from sqlalchemy import select

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.logging import get_logger
from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.trust import TrustScanner
from spark.workers.celery_app import celery_app

log = get_logger(__name__)

_POLICY_VERSION_KEY = "spark:ingest_content_policy:version"


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def stored_policy_version() -> str | None:
    try:
        return _redis_client().get(_POLICY_VERSION_KEY)
    except Exception:
        return None


def persist_policy_version(version: str) -> None:
    try:
        _redis_client().set(_POLICY_VERSION_KEY, version)
    except Exception as exc:
        log.warning("policy_version_persist_failed", error=str(exc)[:120])


async def run_policy_rescan(*, force: bool = False) -> dict[str, Any]:
    scanner = TrustScanner()
    current = scanner.version
    previous = stored_policy_version()
    if not force and previous == current:
        return {"skipped": True, "policy_version": current}

    scanned_docs = 0
    scanned_chunks = 0

    async with AsyncSessionLocal() as session:
        docs = (
            await session.execute(
                select(Document).where(
                    Document.retrieval_enabled.is_(True),
                    Document.chunks_count > 0,
                )
            )
        ).scalars().all()

        for doc in docs:
            if doc.policy_scan_version == current and not force:
                continue
            scanned_docs += 1
            chunks = (
                await session.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.doc_id == doc.doc_id,
                        DocumentChunk.ingest_generation == doc.active_ingest_generation,
                    )
                )
            ).scalars().all()

            document_context = {
                "factory_id": doc.factory_id,
                "machine_id": doc.machine_id,
                "document_type": doc.document_type,
                "document_category": doc.document_category,
                "language": doc.language,
            }
            findings: list[dict[str, Any]] = []
            max_risk = float(doc.content_risk_score or 0.0)

            for chunk in chunks:
                scanned_chunks += 1
                payload = dict(chunk.payload or {})
                payload.setdefault("document_type", doc.document_type)
                result = scanner.scan(
                    text=chunk.content,
                    payload=payload,
                    document_context=document_context,
                )
                if result.findings:
                    findings.extend(result.findings_summary())
                max_risk = max(max_risk, result.risk_score)

            doc.policy_scan_version = current
            doc.content_risk_score = max_risk
            meta = dict(doc.extra_metadata or {})
            if findings:
                meta["policy_findings"] = findings[:50]
                doc.extra_metadata = meta
            # Findings are audit metadata only — do not disable retrieval on rescan.

        await session.commit()

    persist_policy_version(current)
    summary = {
        "skipped": False,
        "policy_version": current,
        "previous_version": previous,
        "scanned_docs": scanned_docs,
        "scanned_chunks": scanned_chunks,
    }
    log.info("policy_rescan_complete", **summary)
    return summary


@celery_app.task(name="spark.workers.tasks_policy_rescan.policy_rescan_task")
def policy_rescan_task(force: bool = False) -> dict[str, Any]:
    return asyncio.run(run_policy_rescan(force=force))
