"""RBAC primitives and auth middleware (app-layer Phase 2)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request, status
from starlette.responses import JSONResponse

from spark.api.platform.errors import api_error_response
from spark.core.auth import TokenError, verify_token
from spark.core.config import settings
from spark.core.logging import bind_request_context, get_logger
from spark.core.stream_auth import (
    is_sse_ticket_route,
    require_ticket_for_sse_route,
    resolve_bearer_token,
    resolve_stream_ticket,
)
from spark.core.stream_ticket_auth import principal_from_validated_stream_ticket
from spark.services.api_key_service import (
    api_key_error_detail,
    is_api_key_token,
    principal_for_api_key,
)
from spark.services.auth_session_cache import fetch_user_auth_state
from spark.services.streams.ticket_store import StreamTicketClaims, TicketConsumeStatus

log = get_logger(__name__)

AccessLevel = Literal["read", "write", "admin"]


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    roles: tuple[str, ...]
    factory_access: dict[str, AccessLevel]
    job_position_ids: tuple[str, ...] = ()
    token_version: int = 0
    privacy_policy_version: str = ""
    is_super_admin: bool = False

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles or self.is_super_admin


SYSTEM_PRINCIPAL = Principal(
    user_id="00000000-0000-0000-0000-000000000000",
    username="system",
    roles=("admin",),
    factory_access={},
    is_super_admin=True,
)


def get_principal(request: Request) -> Principal:
    return getattr(request.state, "principal", SYSTEM_PRINCIPAL)


def _auth_required() -> bool:
    return settings.effective_auth_required


def _can_use_system_principal_fallback() -> bool:
    if settings.effective_auth_required:
        return False
    if settings.spark_profile == "test":
        return (
            os.getenv("SPARK_TESTING") == "1"
            and os.getenv("SPARK_ALLOW_SYSTEM_PRINCIPAL") == "1"
        )
    return settings.app_profile.allow_system_principal_fallback


def require_role(role: str):
    def _dep(request: Request) -> Principal:
        p = get_principal(request)
        if p.is_super_admin or p.is_admin or role in p.roles:
            return p
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{role}' required")

    return _dep


def require_super_admin():
    def _dep(request: Request) -> Principal:
        p = get_principal(request)
        if not p.is_super_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "super admin access required")
        return p

    return _dep


def can_access_factory(p: Principal, factory_id: str, level: AccessLevel = "read") -> bool:
    if p.is_admin:
        return True
    grant = p.factory_access.get(factory_id)
    if grant is None:
        return False
    order = {"read": 0, "write": 1, "admin": 2}
    return order[grant] >= order[level]


def can_write_factory(p: Principal, factory_id: str | None) -> bool:
    if p.is_admin or "operator" in p.roles:
        return True
    order = {"read": 0, "write": 1, "admin": 2}
    if factory_id is None:
        return any(order.get(grant, -1) >= order["write"] for grant in p.factory_access.values())
    grant = p.factory_access.get(factory_id)
    return grant is not None and order[grant] >= order["write"]


def can_release_documents(p: Principal) -> bool:
    return p.is_admin or "release_documents" in p.roles


def enforce_release_documents(p: Principal) -> None:
    if not can_release_documents(p):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "release_documents role required",
        )


def enforce_write_factory(p: Principal, factory_id: str | None) -> None:
    if factory_id is None:
        return
    if not can_write_factory(p, factory_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"no write access to factory {factory_id}",
        )


def accessible_factory_ids(p: Principal) -> list[str] | None:
    if p.is_admin:
        return None
    return list(p.factory_access.keys())


def enforce_factory_access(
    p: Principal,
    factory_id: str | None,
    level: AccessLevel = "read",
) -> None:
    if factory_id is None:
        return
    if not can_access_factory(p, factory_id, level):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"no {level} access to factory {factory_id}",
        )


async def enforce_machine_access(
    session,
    p: Principal,
    machine_id: str,
    level: AccessLevel = "read",
) -> None:
    from spark.db.models.org import Machine

    machine = await session.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "machine not found")
    enforce_factory_access(p, machine.factory_id, level)


async def enforce_rag_filter_access(
    session,
    p: Principal,
    rf,
    level: AccessLevel = "read",
) -> None:
    from spark.db.models.org import Machine
    from spark.services.rag_service import RAGFilter

    if rf is None:
        rf = RAGFilter()
    factory_id = rf.factory_id
    if not factory_id and rf.machine_id:
        machine = await session.get(Machine, rf.machine_id)
        if machine:
            factory_id = machine.factory_id
    enforce_factory_access(p, factory_id, level)
    if factory_id is None and not p.is_admin and _auth_required():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "factory_id or machine_id required for scoped access",
        )


async def _validate_token_freshness(body: dict) -> str | None:
    if not _auth_required():
        return None
    if os.getenv("SPARK_TESTING"):
        return None
    sub = body.get("sub")
    if not sub:
        return "invalid token"
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError:
        return "invalid token"

    claim_version = int(body.get("token_version", 0))
    state = await fetch_user_auth_state(user_id)
    if state is None:
        return "user not found"
    if not state.get("is_active", True):
        return "account inactive"
    if int(state.get("token_version", 0)) != claim_version:
        return "token_stale"
    return None


def principal_from_token(token: str) -> Principal:
    body = verify_token(token)
    return Principal(
        user_id=str(body.get("sub", "")),
        username=str(body.get("username", "")),
        roles=tuple(body.get("roles", []) or []),
        factory_access={k: v for k, v in (body.get("factory_access") or {}).items()},
        job_position_ids=tuple(str(x) for x in (body.get("job_position_ids") or [])),
        token_version=int(body.get("token_version", 0)),
        privacy_policy_version=str(body.get("privacy_policy_version") or ""),
        is_super_admin=bool(body.get("is_super_admin", False)),
    )


def principal_from_stream_ticket(claims: StreamTicketClaims) -> Principal:
    return Principal(
        user_id=claims.user_id,
        username=claims.username,
        roles=claims.roles,
        factory_access={
            k: v for k, v in claims.factory_access.items()  # type: ignore[misc]
        },
        job_position_ids=claims.job_position_ids,
        token_version=claims.token_version,
        privacy_policy_version=claims.privacy_policy_version,
        is_super_admin=claims.is_super_admin,
    )


PUBLIC_PATHS = {
    "/",
    "/healthz",
    "/readyz",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/google/login",
    "/api/v1/auth/google/callback",
    "/api/v1/auth/google/status",
    "/api/v1/auth/oauth/exchange",
    "/api/v1/auth/refresh",
}


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return (
        path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi")
    )


def _unauthorized(request: Request, detail: str, *, code: str | None = None) -> JSONResponse:
    return api_error_response(
        request=request,
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        code=code or "unauthorized",
        retryable=False,
    )


async def auth_middleware(request: Request, call_next):
    if _is_public(request.url.path):
        request.state.principal = SYSTEM_PRINCIPAL
        return await call_next(request)

    required = _auth_required()
    method = request.method.upper()
    path = request.url.path
    sse_route = is_sse_ticket_route(method, path)

    bearer = resolve_bearer_token(request)
    if bearer and is_api_key_token(bearer):
        # Machine credential (external integration). Header-based, so it also
        # authenticates SSE routes directly — one-time stream tickets exist for
        # browser EventSource clients that cannot set Authorization headers.
        principal, err_code = await principal_for_api_key(bearer)
        if principal is None:
            return _unauthorized(request, api_key_error_detail(err_code), code=err_code)
        request.state.principal = principal
        bind_request_context(user_id=principal.user_id)
        return await call_next(request)

    if sse_route and require_ticket_for_sse_route():
        if not request.query_params.get("ticket"):
            return _unauthorized(request, "stream ticket required", code="ticket_required")
        status, ticket_claims = await resolve_stream_ticket(request)
        if status is TicketConsumeStatus.REUSED:
            return _unauthorized(request, "stream ticket already used", code="ticket_reused")
        if status is not TicketConsumeStatus.OK or ticket_claims is None:
            return _unauthorized(request, "invalid stream ticket", code="ticket_invalid")
        principal, err_code = await principal_from_validated_stream_ticket(ticket_claims)
        if principal is None:
            return _unauthorized(
                request,
                err_code or "stream ticket stale",
                code=err_code or "ticket_stale",
            )
        request.state.principal = principal
    else:
        token = resolve_bearer_token(request)
        ticket_claims = None
        ticket_status = TicketConsumeStatus.INVALID
        if not token and request.query_params.get("ticket") and sse_route:
            ticket_status, ticket_claims = await resolve_stream_ticket(request)

        if token:
            try:
                body = verify_token(token)
                stale_reason = await _validate_token_freshness(body)
                if stale_reason:
                    if required:
                        stale_code = "token_stale" if stale_reason == "token_stale" else None
                        return _unauthorized(request, stale_reason, code=stale_code)
                    log.warning("auth_stale_token_dev_mode", reason=stale_reason)
                request.state.principal = principal_from_token(token)
            except TokenError as exc:
                if required:
                    return _unauthorized(request, str(exc))
                log.warning("auth_bad_token_dev_mode", error=str(exc))
                if not _can_use_system_principal_fallback():
                    return _unauthorized(request, str(exc))
                request.state.principal = SYSTEM_PRINCIPAL
        elif ticket_status is TicketConsumeStatus.REUSED:
            return _unauthorized(request, "stream ticket already used", code="ticket_reused")
        elif ticket_claims is not None:
            principal, err_code = await principal_from_validated_stream_ticket(ticket_claims)
            if principal is None:
                return _unauthorized(
                    request,
                    err_code or "stream ticket stale",
                    code=err_code or "ticket_stale",
                )
            request.state.principal = principal
        elif required or not _can_use_system_principal_fallback():
            return _unauthorized(request, "missing bearer token")
        else:
            request.state.principal = SYSTEM_PRINCIPAL

    p = request.state.principal
    bind_request_context(user_id=p.user_id)
    return await call_next(request)
