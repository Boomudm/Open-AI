"""Auth flow tests (issue #48)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spark.core.auth import hash_password, issue_token, verify_password
from spark.core.config import settings
from spark.main import app


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("changeme")
    assert verify_password("changeme", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_issue_and_verify() -> None:
    token = issue_token({"sub": "u1", "username": "admin", "roles": ["admin"]})
    body = __import__("spark.core.auth", fromlist=["verify_token"]).verify_token(token)
    assert body["username"] == "admin"


def test_rag_requires_auth_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    client = TestClient(app)
    res = client.post(
        "/api/v1/rag/query",
        json={"question": "test", "filter": {"machine_id": "MC-001"}},
    )
    assert res.status_code == 401
    monkeypatch.setattr(settings, "auth_required", False)


def test_invalid_bearer_rejected_when_auth_required(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    client = TestClient(app)
    res = client.get("/api/v1/machines", headers={"Authorization": "Bearer invalid.token.here"})
    assert res.status_code == 401
    monkeypatch.setattr(settings, "auth_required", False)


def test_authenticated_request_passes_middleware(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
        }
    )
    client = TestClient(app)
    res = client.get("/api/v1/machines", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code != 401
    monkeypatch.setattr(settings, "auth_required", False)


def test_refresh_rejects_stale_token_version(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "spark.api.v1.endpoints.auth.token_version_matches",
        AsyncMock(return_value=False),
    )
    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "roles": ["admin"],
            "token_version": 0,
        }
    )
    client = TestClient(app)
    res = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "revoked" in res.json()["detail"].lower()
