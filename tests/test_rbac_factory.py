"""Factory-scoped RBAC tests (issue #59)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from rbac_seed_fixtures import SEED, run_rbac_seed
from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.security import Principal, enforce_factory_access
from spark.main import app


def _operator_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "username": "operator_f01",
            "roles": ["employee"],
            "factory_access": {SEED.factory_f01: "read"},
            "token_version": 0,
        }
    )


def test_enforce_factory_access_unit() -> None:
    operator = Principal(
        user_id="u2",
        username="operator_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    admin = Principal(
        user_id="u1",
        username="admin",
        roles=("admin",),
        factory_access={},
    )
    enforce_factory_access(operator, "F-01", "read")
    with pytest.raises(HTTPException) as exc:
        enforce_factory_access(operator, "F-02", "read")
    assert exc.value.status_code == 403
    enforce_factory_access(admin, "F-02", "read")


def test_ingest_denies_read_only_employee() -> None:
    from spark.core.security import can_write_factory, enforce_write_factory

    employee = Principal(
        user_id="u2",
        username="floor_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    assert can_write_factory(employee, "F-01") is False
    with pytest.raises(HTTPException) as exc:
        enforce_write_factory(employee, "F-01")
    assert exc.value.status_code == 403

    plant_operator = Principal(
        user_id="u3",
        username="operator_f01",
        roles=("operator",),
        factory_access={"F-01": "write"},
    )
    assert can_write_factory(plant_operator, "F-01") is True
    enforce_write_factory(plant_operator, "F-01")

    role_operator_read_grant = Principal(
        user_id="u4",
        username="operator_read_f01",
        roles=("operator",),
        factory_access={"F-01": "read"},
    )
    assert can_write_factory(role_operator_read_grant, "F-01") is True
    assert can_write_factory(role_operator_read_grant, None) is True


@pytest.mark.asyncio
async def test_rbac_endpoints_with_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    try:
        run_rbac_seed()
    except Exception as exc:
        pytest.skip(f"Postgres unavailable for RBAC seed: {exc}")

    token = _operator_token()
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_f01 = await client.get(
            "/api/v1/documents",
            params={"factory_id": SEED.factory_f01},
            headers=headers,
        )
        assert res_f01.status_code == 200

        res_f02 = await client.get(
            "/api/v1/documents",
            params={"factory_id": SEED.factory_f02},
            headers=headers,
        )
        assert res_f02.status_code == 403

        admin_token = issue_token(
            {
                "sub": "00000000-0000-0000-0000-000000000001",
                "username": "admin",
                "roles": ["admin"],
                "factory_access": {SEED.factory_f01: "admin", SEED.factory_f02: "admin"},
            }
        )
        res_admin = await client.get(
            "/api/v1/documents",
            params={"factory_id": SEED.factory_f02},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin.status_code == 200

    monkeypatch.setattr(settings, "auth_required", False)
