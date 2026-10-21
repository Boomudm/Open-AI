"""Redis pub/sub stream bus (app-layer Phase 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from spark.core.event_bus import publish_event, subscribe_channel
from spark.services.streams.base import StreamPublisher, StreamSubscriber


class RedisStreamBus(StreamPublisher, StreamSubscriber):
    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        await publish_event(channel, payload)

    def subscribe(
        self,
        channel: str,
        *,
        keepalive_sec: float = 15.0,
    ) -> AsyncIterator[dict[str, Any]]:
        return subscribe_channel(channel, keepalive_sec=keepalive_sec)


redis_stream_bus = RedisStreamBus()
