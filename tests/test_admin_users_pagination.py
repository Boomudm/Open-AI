"""Admin users list pagination response shape."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.main import app


def _admin_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "admin_users_pagination",
            "roles": ["admin"],
            "factory_access": {},
            "job_position_ids": [],
            "token_version": 0,
        }
    )


@pytest.mark.asyncio
async def test_list_admin_users_returns_paginated_shape():
    token = _admin_token()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        res = await client.get("/api/v1/admin/users", params={"page": 1, "page_size": 10})
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert isinstance(body["items"], list)
