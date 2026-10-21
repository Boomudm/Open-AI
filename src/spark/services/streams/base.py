"""Stream bus abstractions (app-layer Phase 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class StreamPublisher(Protocol):
    async def publish(self, channel: str, payload: dict[str, Any]) -> None: ...


class StreamSubscriber(Protocol):
    def subscribe(
        self,
        channel: str,
        *,
        keepalive_sec: float = 15.0,
    ) -> AsyncIterator[dict[str, Any]]: ...
