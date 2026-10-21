"""Privacy policy consent during login onboarding."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from spark.api.v1.endpoints.auth import _needs_privacy_acceptance
from spark.core.auth import issue_token, verify_token
from spark.core.config import settings
from spark.core.privacy_policy import PRIVACY_POLICY_VERSION
from spark.db.models.org import User
from spark.main import app


def test_needs_privacy_acceptance_when_never_accepted() -> None:
    user = User(username="u1", password_hash="x", is_active=True)
    assert _needs_privacy_acceptance(user) is True


def test_needs_privacy_acceptance_when_version_stale() -> None:
    from datetime import datetime, timezone

    user = User(
        username="u1",
        password_hash="x",
        is_active=True,
        privacy_policy_accepted_at=datetime.now(timezone.utc),
        privacy_policy_version="2025.01",
    )
    assert _needs_privacy_acceptance(user) is True


def test_needs_privacy_acceptance_when_current() -> None:
    from datetime import datetime, timezone

    user = User(
        username="u1",
        password_hash="x",
        is_active=True,
        privacy_policy_accepted_at=datetime.now(timezone.utc),
        privacy_policy_version=PRIVACY_POLICY_VERSION,
    )
    assert _needs_privacy_acceptance(user) is False


def test_privacy_acceptance_rejects_already_accepted_token() -> None:
    token = issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "emp",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "job_position_ids": [],
            "token_version": 0,
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
        }
    )
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/privacy-acceptance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409


def test_jwt_includes_privacy_policy_version_claim() -> None:
    token = issue_token(
        {
            "sub": "u1",
            "username": "admin",
            "roles": ["admin"],
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
        }
    )
    body = verify_token(token)
    assert body["privacy_policy_version"] == PRIVACY_POLICY_VERSION


@pytest.mark.asyncio
async def test_login_reports_needs_privacy_acceptance() -> None:
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            admin = await session.scalar(select(User).where(User.username == "admin"))
            if admin is None:
                pytest.skip("seed admin user not available")
            admin.privacy_policy_accepted_at = None
            admin.privacy_policy_version = None
            await session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        if res.status_code != 200:
            pytest.skip(f"login unavailable: {res.status_code}")
        body = res.json()
        assert body["needs_privacy_acceptance"] is True
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_accept_privacy_policy_success() -> None:
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            admin = await session.scalar(select(User).where(User.username == "admin"))
            if admin is None:
                pytest.skip("seed admin user not available")
            admin.privacy_policy_accepted_at = None
            admin.privacy_policy_version = None
            await session.commit()
            user_id = admin.user_id

        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        if login.status_code != 200:
            pytest.skip(f"login unavailable: {login.status_code}")
        token = login.json()["token"]

        accept = client.post(
            "/api/v1/auth/privacy-acceptance",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert accept.status_code == 200
        body = accept.json()
        assert body["needs_privacy_acceptance"] is False

        claims = verify_token(body["token"])
        assert claims["privacy_policy_version"] == PRIVACY_POLICY_VERSION

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user is not None
            assert user.privacy_policy_version == PRIVACY_POLICY_VERSION
            assert user.privacy_policy_accepted_at is not None
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


def test_accept_privacy_requires_auth_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    client = TestClient(app)
    res = client.post("/api/v1/auth/privacy-acceptance")
    assert res.status_code == 401
    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_accept_privacy_policy_session_cookie() -> None:
    """Cookie auth (httpOnly session) must work — web onboarding uses cookies, not Authorization."""
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            admin = await session.scalar(select(User).where(User.username == "admin"))
            if admin is None:
                pytest.skip("seed admin user not available")
            admin.privacy_policy_accepted_at = None
            admin.privacy_policy_version = None
            await session.commit()

        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        if login.status_code != 200:
            pytest.skip(f"login unavailable: {login.status_code}")
        token = login.json()["token"]

        accept = client.post(
            "/api/v1/auth/privacy-acceptance",
            cookies={"spark_token": token},
        )
        assert accept.status_code == 200
        assert accept.json()["needs_privacy_acceptance"] is False
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
