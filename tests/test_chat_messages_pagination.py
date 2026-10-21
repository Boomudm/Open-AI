"""Chat messages list pagination response shape."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.main import app


def _user_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "chat_msgs_user",
            "roles": ["operator"],
            "factory_access": {"F-01": ["read", "write"]},
            "job_position_ids": [],
            "token_version": 0,
        }
    )


@pytest.mark.asyncio
async def test_list_chat_messages_returns_paginated_shape():
    token = _user_token()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        session = (await client.post("/api/v1/chat/sessions", json={})).json()
        session_id = session["session_id"]
        res = await client.get(
            f"/api/v1/chat/{session_id}/messages",
            params={"page": 1, "page_size": 50},
        )
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert isinstance(body["items"], list)
    assert body["total"] >= len(body["items"])
