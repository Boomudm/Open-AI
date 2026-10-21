"""Admin user PATCH integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.org import User
from spark.main import app


def _admin_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "admin_test",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin", "F-02": "admin"},
            "token_version": 0,
        }
    )


@pytest.mark.asyncio
async def test_admin_create_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)
    email = f"newuser_{uuid.uuid4().hex[:8]}@spark.local"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/admin/users",
            json={
                "email": email,
                "full_name": "Test Worker",
                "password": "temppass123",
                "role": "employee",
                "factory_access": [{"factory_id": "F-01", "access_level": "read"}],
            },
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == email
        assert "employee" in body["roles"]

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_admin_patch_user_fields(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == "operator_f01").limit(1))
        ).scalar_one_or_none()
        if user is None:
            pytest.skip("seed user operator_f01 not found")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/v1/admin/users/{user.user_id}",
            json={
                "factory_access": [
                    {"factory_id": "F-01", "access_level": "read"},
                    {"factory_id": "F-02", "access_level": "write"},
                ],
                "is_active": True,
            },
            headers=headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["is_active"] is True
        access = {row["factory_id"]: row["access_level"] for row in body["factory_access"]}
        assert access.get("F-01") == "read"
        assert access.get("F-02") == "write"

    monkeypatch.setattr(settings, "auth_required", False)
