"""Opaque stream tickets (app-layer Phase 2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from spark.core.auth import issue_token
from spark.core.app_profile import AppProfile
from spark.core.cache import Cache
from spark.core.config import settings
from spark.core.security import auth_middleware, get_principal
from spark.services.streams.ticket_store import StreamTicketClaims, consume_stream_ticket, mint_stream_ticket


@pytest.fixture(autouse=True)
def _reset_ticket_cache() -> None:
    Cache.reset_for_tests()
    yield
    Cache.reset_for_tests()


def _claims(**overrides) -> StreamTicketClaims:
    base = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "username": "admin",
        "roles": ("admin",),
        "factory_access": {"F-01": "admin"},
        "job_position_ids": (),
        "token_version": 0,
        "stream_epoch": 0,
        "privacy_policy_version": "",
        "is_super_admin": False,
        "channel": "chat_ask",
        "resource_id": "00000000-0000-0000-0000-000000000010",
    }
    base.update(overrides)
    return StreamTicketClaims(**base)


@pytest.mark.asyncio
async def test_ticket_single_use() -> None:
    ticket = await mint_stream_ticket(_claims())
    first = await consume_stream_ticket(ticket)
    second = await consume_stream_ticket(ticket)

    assert first is not None
    assert first.channel == "chat_ask"
    assert second is None


@pytest.mark.asyncio
async def test_unknown_ticket_rejected() -> None:
    assert await consume_stream_ticket("not-a-valid-ticket") is None
    assert await consume_stream_ticket("") is None


@pytest.mark.asyncio
async def test_stream_middleware_accepts_valid_ticket(monkeypatch: pytest.MonkeyPatch) -> None:

    profile = AppProfile(
        require_ticket_freshness_check=False,
        require_ticket_for_sse=False,
    )
    monkeypatch.setattr(type(settings), "app_profile", property(lambda _self: profile))

    ticket = await mint_stream_ticket(
        _claims(channel="chat_ask", resource_id="00000000-0000-0000-0000-000000000010")
    )

    async def _ok(request: Request) -> JSONResponse:
        return JSONResponse({"principal": get_principal(request).username})

    query = f"ticket={ticket}".encode()
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/00000000-0000-0000-0000-000000000010/ask",
            "raw_path": b"/api/v1/chat/00000000-0000-0000-0000-000000000010/ask",
            "root_path": "",
            "scheme": "http",
            "query_string": query,
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    response = await auth_middleware(req, _ok)
    assert response.status_code == 200
    assert b'"admin"' in response.body


def test_mint_ticket_endpoint_requires_auth() -> None:
    from spark.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/streams/ticket",
        json={"channel": "chat_ask", "resource_id": "00000000-0000-0000-0000-000000000010"},
    )
    assert res.status_code == 401


def test_mint_ticket_endpoint_returns_opaque_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.main import app

    async def _noop_owned_session(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "spark.api.v1.endpoints.streams.require_owned_session",
        _noop_owned_session,
    )

    token = issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
        }
    )
    client = TestClient(app)
    res = client.post(
        "/api/v1/streams/ticket",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": "chat_ask", "resource_id": "00000000-0000-0000-0000-000000000010"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ticket"]
    assert data["expires_in"] > 0
    assert "." not in data["ticket"]
