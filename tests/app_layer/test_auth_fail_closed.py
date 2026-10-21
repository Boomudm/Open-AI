"""Fail-closed auth middleware (app-layer Phase 2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from spark.core.config import settings
from spark.core.security import auth_middleware, get_principal


def _request(
    path: str = "/api/v1/chat/sessions",
    *,
    authorization: str | None = None,
    query_string: bytes = b"",
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if authorization:
        headers.append((b"authorization", authorization.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode("ascii"),
            "root_path": "",
            "scheme": "http",
            "query_string": query_string,
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


async def _ok(request: Request) -> JSONResponse:
    return JSONResponse({"principal": get_principal(request).username})


@pytest.mark.asyncio
async def test_production_missing_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "auth_required", True)

    response = await auth_middleware(_request(), _ok)

    assert response.status_code == 401
    body = response.body.decode()
    assert "missing bearer token" in body


def test_production_chat_sessions_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.app_profile import AppProfile
    from spark.core.cache import Cache
    from spark.main import app

    Cache.reset_for_tests()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "auth_required", True)
    profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        redis_required=False,
        global_rate_limit_rpm=0,
    )
    monkeypatch.setattr(type(settings), "app_profile", property(lambda self: profile))
    client = TestClient(app)

    res = client.get("/api/v1/chat/sessions")

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_test_profile_system_principal_requires_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_TESTING", "1")
    monkeypatch.delenv("SPARK_ALLOW_SYSTEM_PRINCIPAL", raising=False)
    monkeypatch.setattr(settings, "spark_profile", "test")
    monkeypatch.setattr(settings, "auth_required", False)

    response = await auth_middleware(_request("/api/v1/documents"), _ok)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_test_profile_allows_system_principal_with_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_TESTING", "1")
    monkeypatch.setenv("SPARK_ALLOW_SYSTEM_PRINCIPAL", "1")
    monkeypatch.setattr(settings, "spark_profile", "test")
    monkeypatch.setattr(settings, "auth_required", False)

    response = await auth_middleware(_request("/api/v1/documents"), _ok)

    assert response.status_code == 200
    assert response.body == b'{"principal":"system"}'


@pytest.mark.asyncio
async def test_stream_path_rejects_access_token_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.auth import issue_token

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "jwt_secret", "test-production-jwt-secret-value")

    token = issue_token({"sub": "u1", "username": "admin", "roles": ["admin"]})
    query = f"access_token={token}".encode()

    response = await auth_middleware(
        _request("/api/v1/ingest/jobs/00000000-0000-0000-0000-000000000010/stream", query_string=query),
        _ok,
    )

    assert response.status_code == 401
