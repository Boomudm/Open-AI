"""Compliance audit export — retrieval log + WORM chain (Phase 14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS
from spark.compliance.export_gate import (
    check_export_rate_limit,
    enforce_compliance_export,
    export_download_expires_at,
    filter_worm_events_by_classification,
    redact_retrieval_row,
    sign_export_download_token,
)
from spark.compliance.taxonomy import classification_levels, export_settings
from spark.core.database import get_session
from spark.core.security import enforce_factory_access, get_principal
from spark.services.audit_retrieval_service import audit_retrieval_service

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditExportResponse(BaseModel):
    factory_id: str | None
    days: int
    classification_level: str | None = None
    retrieval_rows: int
    worm_events: int
    chain_valid: bool
    download_expires_at: str
    download_token: str
    retrieval_log: list[dict] = Field(default_factory=list)
    worm_audit: list[dict] = Field(default_factory=list)


@router.get("/export", response_model=AuditExportResponse, responses=READ_ERRORS)
async def export_compliance_bundle(
    request: Request,
    factory_id: str | None = Query(None),
    days: int = Query(90, ge=1, le=365),
    classification_level: str | None = Query(
        None,
        description="Filter WORM events by document classification level",
    ),
    session: AsyncSession = Depends(get_session),
) -> AuditExportResponse:
    p = get_principal(request)
    enforce_compliance_export(p)
    await check_export_rate_limit(p.user_id)

    max_days = int(export_settings().get("max_bundle_days") or 365)
    if days > max_days:
        raise HTTPException(400, f"days exceeds max_bundle_days={max_days}")

    if classification_level and classification_level not in classification_levels():
        raise HTTPException(400, f"unknown classification_level={classification_level!r}")

    if factory_id:
        if not p.is_admin and "compliance_officer" not in p.roles:
            enforce_factory_access(p, factory_id, "admin")
    elif not p.is_admin:
        raise HTTPException(403, "factory_id required for scoped compliance export")

    bundle = await audit_retrieval_service.export_compliance_bundle(
        session,
        factory_id=factory_id,
        days=days,
    )

    retrieval_log = [redact_retrieval_row(row) for row in bundle.get("retrieval_log") or []]
    worm_audit = filter_worm_events_by_classification(
        list(bundle.get("worm_audit") or []),
        classification_level=classification_level,
    )

    expires_at = export_download_expires_at()
    download_token = sign_export_download_token(
        user_id=p.user_id,
        factory_id=factory_id,
        days=days,
    )

    return AuditExportResponse(
        factory_id=factory_id,
        days=days,
        classification_level=classification_level,
        retrieval_rows=len(retrieval_log),
        worm_events=len(worm_audit),
        chain_valid=bool(bundle.get("chain_valid")),
        download_expires_at=expires_at.isoformat(),
        download_token=download_token,
        retrieval_log=retrieval_log,
        worm_audit=worm_audit,
    )
