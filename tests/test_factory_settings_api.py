"""Admin factory settings API tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.factory_settings import FactorySettings
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
async def test_get_factory_settings_merges_defaults(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/admin/factories/F-01/settings", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["factory_id"] == "F-01"
        assert body["effective"]["rag"]["top_k_default"] == 6
        assert body["stored"] == {}


@pytest.mark.asyncio
async def test_patch_factory_settings_persists_and_merges(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patch_res = await client.patch(
            "/api/v1/admin/factories/F-01/settings",
            headers=headers,
            json={
                "rag": {"top_k_default": 10, "min_max_score": 0.65},
                "notifications": {
                    "enabled": True,
                    "channels": [{"type": "webhook", "url": "https://example.com/hook"}],
                },
            },
        )
        assert patch_res.status_code == 200
        body = patch_res.json()
        assert body["effective"]["rag"]["top_k_default"] == 10
        assert body["effective"]["rag"]["min_max_score"] == 0.65
        assert body["effective"]["notifications"]["enabled"] is True
        assert body["stored"]["rag"]["top_k_default"] == 10

        get_res = await client.get("/api/v1/admin/factories/F-01/settings", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["effective"]["rag"]["top_k_default"] == 10

    async with AsyncSessionLocal() as session:
        row = await session.get(FactorySettings, "F-01")
        assert row is not None
        await session.delete(row)
        await session.commit()


@pytest.mark.asyncio
async def test_patch_factory_settings_validates_bounds(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            "/api/v1/admin/factories/F-01/settings",
            headers=headers,
            json={"rag": {"top_k_default": 99}},
        )
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_cannot_access_factory_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_employee_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        get_res = await client.get("/api/v1/admin/factories/F-01/settings", headers=headers)
        assert get_res.status_code == 403
        patch_res = await client.patch(
            "/api/v1/admin/factories/F-01/settings",
            headers=headers,
            json={"rag": {"top_k_default": 8}},
        )
        assert patch_res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_factory_settings_not_found(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/admin/factories/F-MISSING/settings", headers=headers)
        assert res.status_code == 404

    monkeypatch.setattr(settings, "auth_required", False)
