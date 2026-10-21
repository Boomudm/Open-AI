"""Admin factory CRUD integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.org import Factory
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
            "factory_access": {"F-01": "admin", "F-02": "admin"},
            "token_version": 0,
        }
    )


def _employee_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "operator_test",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "token_version": 0,
        }
    )


@pytest.mark.asyncio
async def test_admin_list_factories(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/admin/factories", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list)
        assert any(row["factory_id"] == "F-01" for row in body)


@pytest.mark.asyncio
async def test_admin_create_factory(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)
    factory_id = "F-TEST-ADM"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/admin/factories",
            json={
                "factory_id": factory_id,
                "factory_name": "Test Admin Factory",
                "location": "Bangkok",
            },
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["factory_id"] == factory_id
        assert body["factory_name"] == "Test Admin Factory"
        assert body["location"] == "Bangkok"

        dup = await client.post(
            "/api/v1/admin/factories",
            json={"factory_id": factory_id, "factory_name": "Duplicate"},
            headers=headers,
        )
        assert dup.status_code == 409

    async with AsyncSessionLocal() as session:
        row = await session.get(Factory, factory_id)
        assert row is not None
        assert row.factory_name == "Test Admin Factory"
        await session.delete(row)
        await session.commit()


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_factories(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_employee_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_res = await client.get("/api/v1/admin/factories", headers=headers)
        assert list_res.status_code == 403

        create_res = await client.post(
            "/api/v1/admin/factories",
            json={"factory_id": "F-NOPE", "factory_name": "Nope"},
            headers=headers,
        )
        assert create_res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)
