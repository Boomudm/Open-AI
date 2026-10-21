"""API key auth for external integrations — issuance, use, revocation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.api_keys import ApiKey
from spark.db.models.org import Role, User, UserFactoryAccess, UserRole
from spark.main import app
from spark.services.api_key_service import generate_api_key, hash_api_key
from rbac_seed_fixtures import ensure_demo_factories


def _admin_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "apikey_admin",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
            "token_version": 0,
        }
    )


def _employee_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "apikey_employee",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "token_version": 0,
        }
    )


async def _make_service_user(*, factory_id: str = "F-01") -> User:
    await ensure_demo_factories()
    async with AsyncSessionLocal() as session:
        role = (
            await session.execute(select(Role).where(Role.role_code == "employee"))
        ).scalar_one_or_none()
        if role is None:
            role = Role(role_code="employee", description="test seed")
            session.add(role)
            await session.flush()
        user = User(
            username=f"svc_{uuid.uuid4().hex[:10]}",
            full_name="Partner Service Account",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        session.add(
            UserFactoryAccess(user_id=user.user_id, factory_id=factory_id, access_level="read")
        )
        await session.commit()
        await session.refresh(user)
        return user


def test_generate_api_key_shape() -> None:
    plaintext, prefix, key_hash = generate_api_key()
    assert plaintext.startswith("nk_")
    assert prefix == plaintext[:11]
    assert key_hash == hash_api_key(plaintext)
    assert len(key_hash) == 64
    other, _, _ = generate_api_key()
    assert other != plaintext


@pytest.mark.asyncio
async def test_api_key_lifecycle(monkeypatch) -> None:
    """Admin issues a key; the key authenticates; revocation cuts access."""
    monkeypatch.setattr(settings, "auth_required", True)
    user = await _make_service_user()
    admin_headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/admin/api-keys",
            json={"name": "partner-website", "user_id": str(user.user_id)},
            headers=admin_headers,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        api_key = body["api_key"]
        key_id = body["key_id"]
        assert api_key.startswith("nk_")
        assert body["key_prefix"] == api_key[:11]
        assert body["username"] == user.username

        key_headers = {"Authorization": f"Bearer {api_key}"}
        res = await client.get("/api/v1/machines", headers=key_headers)
        assert res.status_code == 200, res.text

        res = await client.get("/api/v1/admin/api-keys", headers=admin_headers)
        assert res.status_code == 200
        listed = [k for k in res.json() if k["key_id"] == key_id]
        assert listed and "api_key" not in listed[0]

        res = await client.post(
            f"/api/v1/admin/api-keys/{key_id}/revoke", headers=admin_headers
        )
        assert res.status_code == 200
        assert res.json()["is_active"] is False

        res = await client.get("/api/v1/machines", headers=key_headers)
        assert res.status_code == 401
        assert res.json()["code"] == "api_key_revoked"

        res = await client.delete(
            f"/api/v1/admin/api-keys/{key_id}", headers=admin_headers
        )
        assert res.status_code == 204


@pytest.mark.asyncio
async def test_api_key_scoped_to_service_account_rbac(monkeypatch) -> None:
    """Key inherits the linked user's factory access — no admin surface."""
    monkeypatch.setattr(settings, "auth_required", True)
    user = await _make_service_user()
    plaintext, prefix, key_hash = generate_api_key()
    async with AsyncSessionLocal() as session:
        session.add(
            ApiKey(name="scoped", key_prefix=prefix, key_hash=key_hash, user_id=user.user_id)
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/admin/api-keys", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_expired_api_key_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    user = await _make_service_user()
    plaintext, prefix, key_hash = generate_api_key()
    async with AsyncSessionLocal() as session:
        session.add(
            ApiKey(
                name="expired",
                key_prefix=prefix,
                key_hash=key_hash,
                user_id=user.user_id,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/machines", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert res.status_code == 401
        assert res.json()["code"] == "api_key_expired"


@pytest.mark.asyncio
async def test_unknown_api_key_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/machines",
            headers={"Authorization": f"Bearer nk_{'0' * 48}"},
        )
        assert res.status_code == 401
        assert res.json()["code"] == "api_key_invalid"


@pytest.mark.asyncio
async def test_create_api_key_requires_admin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/admin/api-keys",
            json={"name": "nope", "user_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {_employee_token()}"},
        )
        assert res.status_code == 403
