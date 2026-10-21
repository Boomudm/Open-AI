"""SSE connection governor enforcement (app-layer v2 Phase 3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from spark.services.streams.connection_governor import (
    AcquireStatus,
    connection_governor,
    ensure_sse_connection,
)


@pytest.fixture(autouse=True)
def _reset_governor() -> None:
    connection_governor.reset_for_tests()
    yield
    connection_governor.reset_for_tests()


def test_sixth_connection_rejected_user_cap() -> None:
    user_id = "user-governor-cap"
    with patch(
        "spark.services.streams.connection_governor.per_user_sse_limit",
        return_value=4,
    ):
        for channel in ("chat_ask", "chat_ask", "ingest_job", "ingest_job"):
            result = connection_governor.try_acquire(user_id=user_id, channel=channel)
            assert result.ok

        sixth = connection_governor.try_acquire(user_id=user_id, channel="chat_ask")
        assert not sixth.ok
        assert sixth.status is AcquireStatus.REJECTED_USER_CAP


def test_release_allows_new_connection() -> None:
    user_id = "user-governor-release"
    for channel in ("chat_ask", "chat_ask", "ingest_job", "ingest_job"):
        connection_governor.try_acquire(user_id=user_id, channel=channel)

    blocked = connection_governor.try_acquire(user_id=user_id, channel="chat_ask")
    assert not blocked.ok
    assert blocked.status is AcquireStatus.REJECTED_CHANNEL_CAP

    connection_governor.release(user_id=user_id, channel="chat_ask")
    again = connection_governor.try_acquire(user_id=user_id, channel="chat_ask")
    assert again.ok


def test_channel_cap_rejects_before_user_cap() -> None:
    user_id = "user-channel-cap"
    for _ in range(2):
        result = connection_governor.try_acquire(user_id=user_id, channel="chat_ask")
        assert result.ok

    third = connection_governor.try_acquire(user_id=user_id, channel="chat_ask")
    assert not third.ok
    assert third.status is AcquireStatus.REJECTED_CHANNEL_CAP


def test_ensure_sse_connection_raises_429() -> None:
    user_id = "user-ensure-429"
    with patch(
        "spark.services.streams.connection_governor.per_user_sse_limit",
        return_value=4,
    ):
        for channel in ("chat_ask", "chat_ask", "ingest_job", "ingest_job"):
            connection_governor.try_acquire(user_id=user_id, channel=channel)

        with pytest.raises(HTTPException) as exc:
            ensure_sse_connection(user_id=user_id, channel="chat_ask")
    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "10"
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "sse_connection_limit"
    assert detail.get("retryable") is True
