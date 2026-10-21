"""Opaque single-use stream tickets (Redis-backed)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from spark.core.cache import Cache
from spark.core.config import settings

StreamChannel = Literal["chat_ask", "ingest_job"]

_TICKET_PREFIX = "spark:stream:ticket:"
_CONSUMED_PREFIX = "spark:stream:ticket:consumed:"


class TicketConsumeStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    REUSED = "reused"


@dataclass(frozen=True)
class StreamTicketClaims:
    user_id: str
    username: str
    roles: tuple[str, ...]
    factory_access: dict[str, str]
    job_position_ids: tuple[str, ...]
    token_version: int
    stream_epoch: int
    privacy_policy_version: str
    is_super_admin: bool
    channel: StreamChannel
    resource_id: str
    minted_at: int = 0

    def to_cache(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": list(self.roles),
            "factory_access": dict(self.factory_access),
            "job_position_ids": list(self.job_position_ids),
            "token_version": self.token_version,
            "stream_epoch": self.stream_epoch,
            "privacy_policy_version": self.privacy_policy_version,
            "is_super_admin": self.is_super_admin,
            "channel": self.channel,
            "resource_id": self.resource_id,
            "minted_at": self.minted_at,
        }

    @classmethod
    def from_cache(cls, raw: dict) -> StreamTicketClaims:
        token_version = int(raw.get("token_version") or 0)
        return cls(
            user_id=str(raw["user_id"]),
            username=str(raw.get("username") or ""),
            roles=tuple(str(r) for r in (raw.get("roles") or [])),
            factory_access={str(k): str(v) for k, v in (raw.get("factory_access") or {}).items()},
            job_position_ids=tuple(str(x) for x in (raw.get("job_position_ids") or [])),
            token_version=token_version,
            stream_epoch=int(raw.get("stream_epoch", token_version)),
            privacy_policy_version=str(raw.get("privacy_policy_version") or ""),
            is_super_admin=bool(raw.get("is_super_admin", False)),
            channel=raw["channel"],
            resource_id=str(raw["resource_id"]),
            minted_at=int(raw.get("minted_at") or 0),
        )


def _ticket_ttl_sec() -> int:
    return max(30, int(settings.app_profile.stream_ticket_ttl_sec))


async def mint_stream_ticket(claims: StreamTicketClaims) -> str:
    ticket = secrets.token_urlsafe(32)
    cache = Cache.get()
    payload = claims.to_cache()
    if not payload.get("minted_at"):
        payload["minted_at"] = int(time.time())
    await cache.set_json(
        f"{_TICKET_PREFIX}{ticket}",
        payload,
        ttl=_ticket_ttl_sec(),
    )
    return ticket


async def consume_stream_ticket_with_status(
    ticket: str,
) -> tuple[TicketConsumeStatus, StreamTicketClaims | None]:
    if not ticket or len(ticket) > 256:
        return TicketConsumeStatus.INVALID, None

    cache = Cache.get()
    stripped = ticket.strip()
    key = f"{_TICKET_PREFIX}{stripped}"
    consumed_key = f"{_CONSUMED_PREFIX}{stripped}"

    raw = await cache.atomic_pop_json(key)
    if isinstance(raw, dict):
        await cache.set_json(consumed_key, {"consumed_at": int(time.time())}, ttl=_ticket_ttl_sec())
        try:
            return TicketConsumeStatus.OK, StreamTicketClaims.from_cache(raw)
        except (KeyError, TypeError, ValueError):
            return TicketConsumeStatus.INVALID, None

    if await cache.get_json(consumed_key) is not None:
        return TicketConsumeStatus.REUSED, None
    return TicketConsumeStatus.INVALID, None


async def consume_stream_ticket(ticket: str) -> StreamTicketClaims | None:
    status, claims = await consume_stream_ticket_with_status(ticket)
    if status == TicketConsumeStatus.OK:
        return claims
    return None
