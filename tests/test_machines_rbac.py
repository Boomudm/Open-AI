"""Factory-scoped RBAC tests for machines API."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from rbac_seed_fixtures import SEED, run_rbac_seed
from spark.core.auth import issue_token
from spark.core.config import settings
from spark.main import app


def _token(*, roles: list[str], factory_access: dict[str, str]) -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000099",
            "username": "rbac_test",
            "roles": roles,
            "factory_access": factory_access,
            "token_version": 0,
        }
    )


@pytest.fixture(scope="module")
def rbac_seed() -> None:
    try:
        run_rbac_seed()
    except Exception as exc:
        pytest.skip(f"Postgres unavailable for RBAC seed: {exc}")


@pytest.mark.asyncio
async def test_create_machine_duplicate_returns_409(monkeypatch, rbac_seed) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {
        "Authorization": f"Bearer {_token(roles=['employee'], factory_access={SEED.factory_f01: 'write'})}"
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/machines",
            json={
                "machine_id": SEED.machine_f01,
                "factory_id": SEED.factory_f01,
                "machine_name": "Duplicate",
            },
            headers=headers,
        )
        assert res.status_code == 409

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_create_machine_write_required(monkeypatch, rbac_seed) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {
        "Authorization": f"Bearer {_token(roles=['employee'], factory_access={SEED.factory_f01: 'read'})}"
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/machines",
            json={
                "machine_id": "MC-RBAC-NEW",
                "factory_id": SEED.factory_f01,
                "machine_name": "New Machine",
            },
            headers=headers,
        )
        assert res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_patch_deactivate_machine(monkeypatch, rbac_seed) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    write_headers = {
        "Authorization": f"Bearer {_token(roles=['employee'], factory_access={SEED.factory_f01: 'write'})}"
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        machine_id = f"MC-RBAC-{uuid.uuid4().hex[:8].upper()}"
        create = await client.post(
            "/api/v1/machines",
            json={
                "machine_id": machine_id,
                "factory_id": SEED.factory_f01,
                "machine_name": "To Deactivate",
            },
            headers=write_headers,
        )
        assert create.status_code == 201

        patch = await client.patch(
            f"/api/v1/machines/{machine_id}",
            json={"is_active": False},
            headers=write_headers,
        )
        assert patch.status_code == 200
        assert patch.json()["is_active"] is False

        listed = await client.get(
            "/api/v1/machines",
            params={"factory_id": SEED.factory_f01},
            headers=write_headers,
        )
        assert listed.status_code == 200
        ids = [m["machine_id"] for m in listed.json()["items"]]
        assert machine_id not in ids

        inactive = await client.get(
            "/api/v1/machines",
            params={
                "factory_id": SEED.factory_f01,
                "include_inactive": "true",
                "q": machine_id,
            },
            headers=write_headers,
        )
        assert inactive.status_code == 200
        inactive_ids = [m["machine_id"] for m in inactive.json()["items"]]
        assert machine_id in inactive_ids

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_include_inactive_denied_for_read_only(monkeypatch, rbac_seed) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    headers = {
        "Authorization": f"Bearer {_token(roles=['employee'], factory_access={SEED.factory_f01: 'read'})}"
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/machines",
            params={"factory_id": SEED.factory_f01, "include_inactive": "true"},
            headers=headers,
        )
        assert res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)
