from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.database import get_session
from spark.core.security import Principal, require_role
from spark.services.system_admin_service import build_system_admin_dashboard, run_system_admin_action

router = APIRouter(prefix="/system-admin", tags=["System Admin"])


class MaintenanceBody(BaseModel):
    enabled: bool
    message: str | None = None


class SystemActionBody(BaseModel):
    message: str | None = None


@router.get("/dashboard")
async def system_admin_dashboard(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    return await build_system_admin_dashboard(session)


@router.post("/actions/clear-cache")
async def clear_cache(
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    return await run_system_admin_action("clear-cache", operator=principal.username)


@router.post("/actions/qdrant-sync")
async def qdrant_sync(
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    return await run_system_admin_action("qdrant-sync", operator=principal.username)


@router.post("/actions/reset-agentic-circuit")
async def reset_agentic_circuit(
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    return await run_system_admin_action("reset-agentic", operator=principal.username)


@router.post("/actions/reset-rag-circuit")
async def reset_rag_circuit(
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    return await run_system_admin_action("reset-rag", operator=principal.username)


@router.post("/actions/maintenance")
async def toggle_maintenance(
    body: MaintenanceBody,
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    action = "maintenance-on" if body.enabled else "maintenance-off"
    try:
        return await run_system_admin_action(
            action,
            operator=principal.username,
            message=body.message,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
