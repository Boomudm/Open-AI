"""Production auth safety tests for QA A4."""

from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from spark.core.config import settings
from spark.core.security import auth_middleware, get_principal

PRODUCTION_JWT_SECRET = "test-production-jwt-secret"


def _production_baseline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "jwt_secret", PRODUCTION_JWT_SECRET)
    monkeypatch.setattr(settings, "llm_profile", "gemma")
    monkeypatch.setattr(settings, "postgres_password", "prod-postgres-password")
    monkeypatch.setattr(settings, "cors_origins", "https://neo.example.com")
    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.0/8")


def _request(path: str = "/api/v1/machines", authorization: str | None = None) -> Request:
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
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


async def _ok(request: Request) -> JSONResponse:
    return JSONResponse({"principal": get_principal(request).username})


@pytest.mark.asyncio
async def test_production_rejects_invalid_bearer_when_auth_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "jwt_secret", PRODUCTION_JWT_SECRET)

    response = await auth_middleware(
        _request(authorization="Bearer invalid.token.here"),
        _ok,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_production_requires_token_when_auth_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "jwt_secret", PRODUCTION_JWT_SECRET)

    response = await auth_middleware(_request(), _ok)

    assert response.status_code == 401
    assert settings.effective_auth_required is True


@pytest.mark.asyncio
async def test_development_demo_still_allows_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "auth_required", False)

    response = await auth_middleware(_request(), _ok)

    assert response.status_code == 200
    assert response.body == b'{"principal":"system"}'


def test_production_rejects_default_jwt_secret(monkeypatch) -> None:
    _production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "jwt_secret", "dev-secret-change-me")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_for_production()


def test_production_rejects_empty_jwt_secret(monkeypatch) -> None:
    _production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "jwt_secret", "")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_for_production()


def test_production_accepts_configured_jwt_secret(monkeypatch) -> None:
    _production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "jwt_secret", "production-only-secret-value")

    settings.validate_for_production()


def test_production_rejects_demo_llm_profile(monkeypatch) -> None:
    _production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "jwt_secret", "production-only-secret-value")
    monkeypatch.setattr(settings, "llm_profile", "demo")

    with pytest.raises(RuntimeError, match="LLM_PROFILE"):
        settings.validate_for_production()


def test_development_allows_default_jwt_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "jwt_secret", "dev-secret-change-me")

    settings.validate_for_production()
