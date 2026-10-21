"""Release quarantined documents — enqueue index-from-artifact."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.database import get_session
from spark.core.logging import get_logger
from spark.core.security import (
    enforce_release_documents,
    enforce_write_factory,
    get_principal,
)
from spark.db.models.docs import Document
from spark.schemas.documents import DocumentOut
from spark.services.document_access_service import (
    can_access_document,
    log_document_access,
    restricted_position_ids_for_docs,
)

log = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


class PolicyFindingOut(BaseModel):
    rule_id: str
    severity: str
    message: str
    matched_text: str | None = None


class PolicyFindingsResponse(BaseModel):
    doc_id: UUID
    policy_scan_version: str | None
    content_risk_score: float | None
    ingest_status: str
    retrieval_enabled: bool
    findings: list[PolicyFindingOut] = Field(default_factory=list)


class DocumentReleaseResponse(BaseModel):
    document: DocumentOut
    released: bool
    index_task_id: str | None = None


def _document_out(doc: Document, positions: list[UUID]) -> DocumentOut:
    return DocumentOut.model_validate(doc, from_attributes=True).model_copy(
        update={"visible_position_ids": positions}
    )


def _policy_findings_from_doc(doc: Document) -> list[dict[str, Any]]:
    if isinstance(doc.policy_findings_json, list):
        return list(doc.policy_findings_json)
    meta = doc.extra_metadata if isinstance(doc.extra_metadata, dict) else {}
    raw = meta.get("policy_findings") or []
    return list(raw) if isinstance(raw, list) else []


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.get("/{doc_id}/policy-findings", response_model=PolicyFindingsResponse, responses=READ_ERRORS)
async def get_policy_findings(
    doc_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if not await can_access_document(session, p, doc):
        raise HTTPException(403, "no access to document")
    if not (p.is_admin or doc.ingest_status in ("quarantined", "pending_release")):
        if doc.ingest_status not in ("quarantined", "pending_release", "completed", "partial", "blocked"):
            raise HTTPException(403, "policy findings not available for this document")

    findings = _policy_findings_from_doc(doc)
    return PolicyFindingsResponse(
        doc_id=doc.doc_id,
        policy_scan_version=doc.policy_scan_version,
        content_risk_score=doc.content_risk_score,
        ingest_status=doc.ingest_status,
        retrieval_enabled=doc.retrieval_enabled,
        findings=[PolicyFindingOut.model_validate(item) for item in findings],
    )


@router.post("/{doc_id}/release", response_model=DocumentReleaseResponse, responses=WRITE_ERRORS)
async def release_quarantined_document(
    doc_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_release_documents(p)

    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    enforce_write_factory(p, doc.factory_id)

    if doc.ingest_status not in ("quarantined", "pending_release"):
        raise HTTPException(409, "document is not awaiting release")

    if doc.created_by and str(doc.created_by) == p.user_id and not p.is_admin:
        raise HTTPException(
            403,
            "uploader cannot release their own document — separation of duties",
        )

    if not doc.quarantine_artifact_uri:
        raise HTTPException(409, "quarantine artifact missing — cannot release")

    # Find the job this document was quarantined under so the re-index task can
    # update it in place instead of leaving it stuck at "pending_release"
    # forever — index_quarantined_document_task previously ran with no job_id
    # at all, so the release never touched ingestion_jobs, only the Document
    # row. From the UI's perspective the job looked exactly like it "didn't
    # continue" even after a successful release.
    from spark.db.models.ingestion import IngestionJob

    existing_job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.doc_id == doc_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    from spark.workers.tasks_trust_release import index_quarantined_document_task

    async_result = index_quarantined_document_task.delay(
        str(doc_id), str(existing_job.job_id) if existing_job else None
    )

    now = datetime.now(tz=timezone.utc)
    doc.ingest_status = "indexing"
    doc.released_at = now
    try:
        doc.released_by = uuid.UUID(p.user_id)
    except ValueError:
        doc.released_by = None
    if existing_job:
        existing_job.status = "indexing"
        existing_job.celery_task_id = async_result.id

    await log_document_access(
        session,
        doc_id=doc.doc_id,
        user_id=p.user_id,
        action="release",
        ip=_client_ip(request),
    )
    await session.commit()
    from spark.services.acl.mutation_hooks import on_document_released

    await on_document_released(
        session,
        factory_id=doc.factory_id,
        doc_id=doc.doc_id,
    )
    await session.refresh(doc)

    findings = _policy_findings_from_doc(doc)
    log.info(
        "document_released",
        doc_id=str(doc_id),
        released_by=p.user_id,
        factory_id=doc.factory_id,
        finding_count=len(findings),
        index_task_id=async_result.id,
    )
    from spark.audit.worm_sink import EVENT_QUARANTINE_RELEASE, schedule_worm_audit

    schedule_worm_audit(
        EVENT_QUARANTINE_RELEASE,
        actor_id=p.user_id,
        factory_id=doc.factory_id,
        payload={
            "doc_id": str(doc_id),
            "document_type": doc.document_type,
            "finding_count": len(findings),
            "index_task_id": async_result.id,
        },
    )

    position_map = await restricted_position_ids_for_docs(session, [doc.doc_id])
    return DocumentReleaseResponse(
        document=_document_out(doc, position_map.get(doc.doc_id, [])),
        released=True,
        index_task_id=async_result.id,
    )
