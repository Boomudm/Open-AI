"""SSE stream ticket exchange (app-layer Phase 2)."""

from __future__ import annotations

import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.core.database import get_session
from spark.core.security import (
    Principal,
    get_principal,
)
from spark.db.models.ingestion import IngestionJob
from spark.services.auth_session_cache import fetch_user_auth_state
from spark.services.chat_session_access import require_owned_session
from spark.services.streams.ticket_store import StreamChannel, StreamTicketClaims, mint_stream_ticket

router = APIRouter(prefix="/streams", tags=["Streams"])


class StreamTicketRequest(BaseModel):
    channel: Literal["chat_ask", "ingest_job"]
    resource_id: str = Field(min_length=1, max_length=128)


class StreamTicketResponse(BaseModel):
    ticket: str
    expires_in: int
    remaining_connections: int | None = None


def _claims_from_principal(
    p: Principal,
    *,
    channel: StreamChannel,
    resource_id: str,
    stream_epoch: int,
) -> StreamTicketClaims:
    return StreamTicketClaims(
        user_id=p.user_id,
        username=p.username,
        roles=p.roles,
        factory_access=dict(p.factory_access),
        job_position_ids=p.job_position_ids,
        token_version=p.token_version,
        stream_epoch=stream_epoch,
        privacy_policy_version=p.privacy_policy_version,
        is_super_admin=p.is_super_admin,
        channel=channel,
        resource_id=resource_id,
    )


async def _authorize_ticket_request(
    session: AsyncSession,
    p: Principal,
    body: StreamTicketRequest,
) -> None:
    if body.channel == "chat_ask":
        try:
            session_id = UUID(body.resource_id)
        except ValueError as exc:
            raise HTTPException(400, "invalid session_id") from exc
        await require_owned_session(session, session_id, p)
        return

    if body.channel == "ingest_job":
        try:
            job_id = UUID(body.resource_id)
        except ValueError as exc:
            raise HTTPException(400, "invalid job_id") from exc
        job = await session.get(IngestionJob, job_id)
        if job is None:
            raise HTTPException(404, "ingest job not found")
        from spark.core.security import enforce_factory_access

        factory_id = job.factory_id
        if factory_id:
            enforce_factory_access(p, factory_id, "read")
        return

    raise HTTPException(400, "unsupported stream channel")


@router.post(
    "/ticket",
    response_model=StreamTicketResponse,
    responses=WRITE_ERRORS,
    summary="Exchange session auth for SSE stream ticket",
    description=(
        "Mint a single-use opaque ticket (120s TTL) for SSE/stream endpoints. "
        "Connect with `?ticket=` only — JWT must not appear in query strings."
    ),
)
async def create_stream_ticket(
    request: Request,
    body: StreamTicketRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamTicketResponse:
    """Exchange session cookie auth for a single-use opaque SSE ticket."""
    p = get_principal(request)
    if p.username == "system":
        raise HTTPException(401, "missing bearer token")

    await _authorize_ticket_request(session, p, body)
    try:
        user_id = uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid principal user_id") from exc
    state = await fetch_user_auth_state(user_id)
    stream_epoch = int((state or {}).get("stream_epoch", p.token_version))
    claims = _claims_from_principal(
        p,
        channel=body.channel,
        resource_id=body.resource_id,
        stream_epoch=stream_epoch,
    )
    ticket = await mint_stream_ticket(claims)
    from spark.core.config import settings
    from spark.services.streams.connection_governor import connection_governor

    return StreamTicketResponse(
        ticket=ticket,
        expires_in=settings.app_profile.stream_ticket_ttl_sec,
        remaining_connections=connection_governor.remaining_for_user(p.user_id or "anonymous"),
    )
