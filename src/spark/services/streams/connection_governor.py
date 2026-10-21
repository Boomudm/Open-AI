"""Enforced per-user SSE connection budget (app-layer v2 Phase 3)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from fastapi import HTTPException, status

from spark.api.platform.sse_policy import per_channel_sse_limit, per_user_sse_limit
from spark.core.logging import get_logger
from spark.core.metrics import sse_connections_active, sse_connections_rejected_total

log = get_logger(__name__)


class AcquireStatus(str, Enum):
    OK = "ok"
    REJECTED_USER_CAP = "rejected_user_cap"
    REJECTED_CHANNEL_CAP = "rejected_channel_cap"


@dataclass(frozen=True)
class AcquireResult:
    status: AcquireStatus

    @property
    def ok(self) -> bool:
        return self.status is AcquireStatus.OK


@dataclass
class ConnectionGovernor:
    _by_user: dict[str, int] = field(default_factory=dict)
    _by_user_channel: dict[tuple[str, str], int] = field(default_factory=dict)

    def _user_key(self, user_id: str) -> str:
        return user_id or "anonymous"

    def try_acquire(self, *, user_id: str, channel: str) -> AcquireResult:
        key = self._user_key(user_id)
        user_total = self._by_user.get(key, 0)
        user_cap = per_user_sse_limit()
        if user_total >= user_cap:
            sse_connections_rejected_total.labels(reason="user_cap", channel=channel).inc()
            log.debug("sse_connection_rejected", user_id=key, channel=channel, reason="user_cap")
            return AcquireResult(AcquireStatus.REJECTED_USER_CAP)

        channel_key = (key, channel)
        channel_total = self._by_user_channel.get(channel_key, 0)
        channel_cap = per_channel_sse_limit(channel)
        if channel_total >= channel_cap:
            sse_connections_rejected_total.labels(reason="channel_cap", channel=channel).inc()
            log.debug("sse_connection_rejected", user_id=key, channel=channel, reason="channel_cap")
            return AcquireResult(AcquireStatus.REJECTED_CHANNEL_CAP)

        self._by_user[key] = user_total + 1
        self._by_user_channel[channel_key] = channel_total + 1
        sse_connections_active.labels(channel=channel).inc()
        log.debug("sse_connection_open", user_id=key, channel=channel, user_total=user_total + 1)
        return AcquireResult(AcquireStatus.OK)

    def release(self, *, user_id: str, channel: str) -> None:
        key = self._user_key(user_id)
        channel_key = (key, channel)
        user_total = self._by_user.get(key, 0)
        if user_total <= 1:
            self._by_user.pop(key, None)
        else:
            self._by_user[key] = user_total - 1

        channel_total = self._by_user_channel.get(channel_key, 0)
        if channel_total <= 1:
            self._by_user_channel.pop(channel_key, None)
        else:
            self._by_user_channel[channel_key] = channel_total - 1

        sse_connections_active.labels(channel=channel).dec()
        log.debug("sse_connection_close", user_id=key, channel=channel)

    def remaining_for_user(self, user_id: str) -> int:
        key = self._user_key(user_id)
        used = self._by_user.get(key, 0)
        return max(0, per_user_sse_limit() - used)

    @property
    def active_total(self) -> int:
        return sum(self._by_user.values())

    def reset_for_tests(self) -> None:
        self._by_user.clear()
        self._by_user_channel.clear()


connection_governor = ConnectionGovernor()


def raise_sse_connection_limit(*, reason: AcquireStatus, channel: str) -> None:
    detail = "SSE connection limit exceeded"
    code = "sse_connection_limit"
    if reason is AcquireStatus.REJECTED_CHANNEL_CAP:
        detail = f"SSE connection limit exceeded for channel '{channel}'"
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "detail": detail,
            "code": code,
            "reason": reason.value,
            "retryable": True,
        },
        headers={"Retry-After": "10"},
    )


def ensure_sse_connection(*, user_id: str, channel: str) -> None:
    result = connection_governor.try_acquire(user_id=user_id, channel=channel)
    if not result.ok:
        raise_sse_connection_limit(reason=result.status, channel=channel)


@contextmanager
def sse_connection_slot(*, user_id: str, channel: str) -> Iterator[None]:
    ensure_sse_connection(user_id=user_id, channel=channel)
    try:
        yield
    finally:
        connection_governor.release(user_id=user_id, channel=channel)
