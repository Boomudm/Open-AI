"""Phase 12 — auth bypass and stream ticket security regressions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from spark.core.auth import issue_token
from spark.core.app_profile import AppProfile
from spark.core.config import settings
from spark.core.security import PUBLIC_PATHS, auth_middleware
from spark.services.streams.ticket_store import (
    StreamTicketClaims,
    TicketConsumeStatus,
    consume_stream_ticket,
    consume_stream_ticket_with_status,
    mint_stream_ticket,
)

PROTECTED_GET_ROUTES = (
    "/api/v1/chat/sessions",
    "/api/v1/machines",
    "/api/v1/factories",
    "/api/v1/streams/ticket",
)


def _patch_production_app_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        redis_required=False,
        global_rate_limit_rpm=0,
        live_token_stream_default=True,
    )
    monkeypatch.setattr(type(settings), "app_profile", property(lambda self: profile))


def _production_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from spark.core.cache import Cache
    from spark.main import app

    Cache.reset_for_tests()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "jwt_secret", "test-production-jwt-secret-value")
    _patch_production_app_profile(monkeypatch)
    return TestClient(app)


def test_protected_api_routes_return_401_without_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _production_client(monkeypatch)
    for path in PROTECTED_GET_ROUTES:
        res = client.get(path)
        assert res.status_code == 401, path
        body = res.json()
        assert body.get("code") == "unauthorized"
        assert "trace_id" in body


def test_public_paths_remain_unauthenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _production_client(monkeypatch)
    for path in ("/healthz", "/readyz"):
        assert path in PUBLIC_PATHS
        res = client.get(path)
        assert res.status_code in {200, 503}, path


@pytest.mark.asyncio
async def test_query_jwt_rejected_on_stream_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "jwt_secret", "test-production-jwt-secret-value")

    token = issue_token({"sub": "u1", "username": "admin", "roles": ["admin"]})
    query = f"access_token={token}".encode()

    async def _ok(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/ingest/jobs/00000000-0000-0000-0000-000000000010/stream",
            "raw_path": b"/api/v1/ingest/jobs/00000000-0000-0000-0000-000000000010/stream",
            "root_path": "",
            "scheme": "http",
            "query_string": query,
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    response = await auth_middleware(req, _ok)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_consumed_stream_ticket_rejected() -> None:
    claims = StreamTicketClaims(
        user_id="00000000-0000-0000-0000-000000000001",
        username="admin",
        roles=("admin",),
        factory_access={"F-01": "admin"},
        job_position_ids=(),
        token_version=0,
        stream_epoch=0,
        privacy_policy_version="",
        is_super_admin=False,
        channel="chat_ask",
        resource_id="00000000-0000-0000-0000-000000000010",
    )
    ticket = await mint_stream_ticket(claims)
    assert await consume_stream_ticket(ticket) is not None
    status, _ = await consume_stream_ticket_with_status(ticket)
    assert status is TicketConsumeStatus.REUSED


@pytest.mark.asyncio
async def test_sse_route_rejects_bearer_without_ticket_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.core.app_profile import AppProfile

    profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        require_ticket_for_sse=True,
        require_ticket_freshness_check=False,
    )
    monkeypatch.setattr(type(settings), "app_profile", property(lambda _self: profile))
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "jwt_secret", "test-production-jwt-secret-value")

    token = issue_token({"sub": "u1", "username": "admin", "roles": ["admin"]})

    async def _ok(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/ingest/jobs/00000000-0000-0000-0000-000000000010/stream",
            "raw_path": b"/api/v1/ingest/jobs/00000000-0000-0000-0000-000000000010/stream",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    response = await auth_middleware(req, _ok)
    assert response.status_code == 401
    body = response.body
    assert b"ticket_required" in body
