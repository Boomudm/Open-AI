"""Atomic stream ticket consume (app-layer v2 Phase 2)."""

from __future__ import annotations

import asyncio

import pytest

from spark.core.cache import Cache
from spark.services.streams.ticket_store import (
    StreamTicketClaims,
    TicketConsumeStatus,
    consume_stream_ticket_with_status,
    mint_stream_ticket,
)


def _claims() -> StreamTicketClaims:
    return StreamTicketClaims(
        user_id="00000000-0000-0000-0000-000000000001",
        username="admin",
        roles=("admin",),
        factory_access={"F-01": "admin"},
        job_position_ids=(),
        token_version=0,
        stream_epoch=0,
        privacy_policy_version="",
        is_super_admin=False,
        channel="chat_ask",
        resource_id="00000000-0000-0000-0000-000000000010",
    )


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    Cache.reset_for_tests()
    yield
    Cache.reset_for_tests()


@pytest.mark.asyncio
async def test_concurrent_consume_exactly_one_success() -> None:
    ticket = await mint_stream_ticket(_claims())

    async def _consume() -> TicketConsumeStatus:
        status, _ = await consume_stream_ticket_with_status(ticket)
        return status

    results = await asyncio.gather(*[_consume() for _ in range(10)])
    assert results.count(TicketConsumeStatus.OK) == 1
    assert results.count(TicketConsumeStatus.REUSED) + results.count(TicketConsumeStatus.INVALID) == 9


@pytest.mark.asyncio
async def test_second_consume_reports_reused() -> None:
    ticket = await mint_stream_ticket(_claims())
    first, _ = await consume_stream_ticket_with_status(ticket)
    second, _ = await consume_stream_ticket_with_status(ticket)
    assert first is TicketConsumeStatus.OK
    assert second is TicketConsumeStatus.REUSED
