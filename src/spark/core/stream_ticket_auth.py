"""Stream ticket freshness validation (app-layer v2 Phase 2)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from spark.core.config import settings
from spark.services.auth_session_cache import fetch_user_auth_state
from spark.services.streams.ticket_store import StreamTicketClaims

if TYPE_CHECKING:
    from spark.core.security import Principal


async def validate_stream_ticket_claims(claims: StreamTicketClaims) -> str | None:
    """Return error reason string, or None when claims are live-valid."""
    if not settings.app_profile.require_ticket_freshness_check:
        return None

    try:
        user_id = uuid.UUID(str(claims.user_id))
    except ValueError:
        return "invalid token"

    state = await fetch_user_auth_state(user_id)
    if state is None:
        return "user not found"
    if not state.get("is_active", True):
        return "account inactive"

    live_version = int(state.get("token_version", 0))
    if live_version != int(claims.token_version):
        return "token_stale"

    live_epoch = int(state.get("stream_epoch", live_version))
    if live_epoch != int(claims.stream_epoch):
        return "token_stale"

    return None


async def principal_from_validated_stream_ticket(
    claims: StreamTicketClaims,
) -> tuple[Principal | None, str | None]:
    """Validate live auth state then materialize principal."""
    stale = await validate_stream_ticket_claims(claims)
    if stale:
        code = "ticket_stale" if stale == "token_stale" else stale
        return None, code
    from spark.core.security import principal_from_stream_ticket

    return principal_from_stream_ticket(claims), None
