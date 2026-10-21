"""Factory list API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.main import app
from rbac_seed_fixtures import ensure_demo_factories


@pytest.fixture(autouse=True)
async def _demo_factories() -> None:
    await ensure_demo_factories()


def _admin_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "admin_test",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
            "token_version": 0,
        }
    )


def _employee_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "operator_test",
            "roles": ["employee"],
            "factory_access": {"F-01": "read", "F-02": "read"},
            "token_version": 0,
        }
    )


@pytest.mark.asyncio
async def test_list_factories_admin_sees_all(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/factories", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list)
        ids = {row["factory_id"] for row in body}
        assert "F-01" in ids
        assert all("factory_name" in row for row in body)


@pytest.mark.asyncio
async def test_list_factories_scoped_user(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_employee_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/factories", headers=headers)
        assert res.status_code == 200
        ids = {row["factory_id"] for row in res.json()}
        assert ids <= {"F-01", "F-02"}

    monkeypatch.setattr(settings, "auth_required", False)
