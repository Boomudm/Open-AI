"""Stream ticket freshness after revocation (app-layer v2 Phase 2)."""

from __future__ import annotations

import uuid

import pytest

from spark.core.app_profile import AppProfile
from spark.core.cache import Cache
from spark.core.config import settings
from spark.core.stream_ticket_auth import validate_stream_ticket_claims
from spark.services.auth_session import token_version_cache_key
from spark.services.streams.ticket_store import StreamTicketClaims, mint_stream_ticket


def _claims(**overrides) -> StreamTicketClaims:
    base = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "username": "admin",
        "roles": ("admin",),
        "factory_access": {"F-01": "admin"},
        "job_position_ids": (),
        "token_version": 1,
        "stream_epoch": 1,
        "privacy_policy_version": "",
        "is_super_admin": False,
        "channel": "chat_ask",
        "resource_id": "00000000-0000-0000-0000-000000000010",
    }
    base.update(overrides)
    return StreamTicketClaims(**base)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    Cache.reset_for_tests()
    yield
    Cache.reset_for_tests()


@pytest.mark.asyncio
async def test_stale_token_version_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = AppProfile(require_ticket_freshness_check=True, require_ticket_for_sse=True)
    monkeypatch.setattr(type(settings), "app_profile", property(lambda _self: profile))

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    await Cache.get().set_json(
        token_version_cache_key(user_id),
        {"token_version": 2, "stream_epoch": 2, "is_active": True},
        ttl=60,
    )

    claims = _claims(token_version=1, stream_epoch=1)
    assert await validate_stream_ticket_claims(claims) == "token_stale"


@pytest.mark.asyncio
async def test_deactivated_user_ticket_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = AppProfile(require_ticket_freshness_check=True)
    monkeypatch.setattr(type(settings), "app_profile", property(lambda _self: profile))

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    await Cache.get().set_json(
        token_version_cache_key(user_id),
        {"token_version": 1, "stream_epoch": 1, "is_active": False},
        ttl=60,
    )

    assert await validate_stream_ticket_claims(_claims()) == "account inactive"


@pytest.mark.asyncio
async def test_minted_ticket_invalid_after_epoch_bump(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = AppProfile(require_ticket_freshness_check=True)
    monkeypatch.setattr(type(settings), "app_profile", property(lambda _self: profile))

    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    await Cache.get().set_json(
        token_version_cache_key(user_id),
        {"token_version": 1, "stream_epoch": 1, "is_active": True},
        ttl=60,
    )

    ticket = await mint_stream_ticket(_claims())
    await Cache.get().set_json(
        token_version_cache_key(user_id),
        {"token_version": 2, "stream_epoch": 2, "is_active": True},
        ttl=60,
    )

    from spark.services.streams.ticket_store import consume_stream_ticket_with_status

    status, claims = await consume_stream_ticket_with_status(ticket)
    assert status.value == "ok"
    assert claims is not None
    assert await validate_stream_ticket_claims(claims) == "token_stale"
