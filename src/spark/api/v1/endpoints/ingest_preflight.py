"""Ingest pre-flight validation — estimate cost without enqueueing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.api.upload_utils import read_upload_bounded
from spark.core.config import settings
from spark.core.database import get_session
from spark.core.security import enforce_write_factory, get_principal
from spark.ingestion.budget import ResourceBudget
from spark.ingestion.preflight.validator import run_ingest_preflight
from spark.services.ingest_scope import resolve_ingest_factory_id

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


class PolicyHintOut(BaseModel):
    rule_id: str
    severity: str
    message: str


class IngestPreflightResponse(BaseModel):
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    estimated_pages: int | None = None
    estimated_chunks: int | None = None
    ocr_required: bool = False
    budget: ResourceBudget | None = None
    policy_hints: list[PolicyHintOut] = Field(default_factory=list)
    quality_tags: list[str] = Field(default_factory=list)
    document_type: str | None = None


@router.post("/preflight", response_model=IngestPreflightResponse, responses=WRITE_ERRORS)
async def ingest_preflight(
    request: Request,
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    factory_id: str | None = Form(None),
    machine_id: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> IngestPreflightResponse:
    p = get_principal(request)
    resolved_factory_id = await resolve_ingest_factory_id(
        session,
        factory_id=factory_id,
        machine_id=machine_id,
    )
    enforce_write_factory(p, resolved_factory_id)

    if not file.filename:
        raise HTTPException(400, "missing filename")

    raw_bytes = await read_upload_bounded(file, settings.max_upload_bytes)
    factory_cfg: dict = {}
    if resolved_factory_id:
        from spark.services.factory_config_service import factory_config_service

        factory_cfg = await factory_config_service.resolve(session, resolved_factory_id)

    result = run_ingest_preflight(
        filename=file.filename,
        raw_bytes=raw_bytes,
        document_type=document_type,
        factory_id=resolved_factory_id,
        machine_id=machine_id,
        factory_cfg=factory_cfg,
    )
    return IngestPreflightResponse(
        accepted=result.accepted,
        reasons=result.reasons,
        estimated_pages=result.estimated_pages,
        estimated_chunks=result.estimated_chunks,
        ocr_required=result.ocr_required,
        budget=result.budget,
        policy_hints=[
            PolicyHintOut(rule_id=h.rule_id, severity=h.severity, message=h.message)
            for h in result.policy_hints
        ],
        quality_tags=result.quality_tags,
        document_type=result.document_type,
    )
