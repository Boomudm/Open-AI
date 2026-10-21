"""Phase 14 — compliance audit export RBAC."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from spark.compliance.export_gate import enforce_compliance_export
from spark.core.auth import issue_token
from spark.core.security import Principal
from spark.main import app


def test_compliance_officer_allowed_unit() -> None:
    officer = Principal(
        user_id="u3",
        username="compliance",
        roles=("compliance_officer",),
        factory_access={"F-01": "admin"},
    )
    enforce_compliance_export(officer)


def test_unauthorized_role_rejected_unit() -> None:
    operator = Principal(
        user_id="u2",
        username="operator_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    with pytest.raises(HTTPException) as exc:
        enforce_compliance_export(operator)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_denies_non_compliance_role() -> None:
    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "username": "operator_f01",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "token_version": 0,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/audit/export?factory_id=F-01",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_allows_compliance_officer() -> None:
    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000004",
            "username": "compliance",
            "roles": ["compliance_officer"],
            "factory_access": {"F-01": "admin"},
            "token_version": 0,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/audit/export?factory_id=F-01&days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "chain_valid" in body
    assert "download_token" in body
    assert "download_expires_at" in body


@pytest.mark.asyncio
async def test_audit_export_allows_admin() -> None:
    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "roles": ["admin"],
            "factory_access": {},
            "token_version": 0,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/audit/export?days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "worm_audit" in body
