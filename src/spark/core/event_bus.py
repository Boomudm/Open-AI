"""Redis pub/sub for SSE fan-out across API instances."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from spark.core.cache import Cache
from spark.core.logging import get_logger
from spark.core.metrics import event_bus_dropped_total

log = get_logger(__name__)

OPTIMIZATION_CHANNEL = "spark:optimization"
ALERTS_CHANNEL = "spark:alerts"
INGEST_CHANNEL = "spark:ingest"


def ingest_job_channel(job_id: str) -> str:
    return f"spark:ingest:{job_id}"


_mem_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
_mem_lock = asyncio.Lock()


def _enqueue_with_backpressure(
    queue: asyncio.Queue[dict[str, Any]],
    payload: dict[str, Any],
    *,
    channel: str,
) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            event_bus_dropped_total.labels(channel=channel).inc()
            log.debug("event_bus_dropped", channel=channel)


async def _fanout_local(channel: str, payload: dict[str, Any]) -> None:
    async with _mem_lock:
        queues = list(_mem_subscribers.get(channel, []))
    for queue in queues:
        _enqueue_with_backpressure(queue, payload, channel=channel)


async def publish_event(channel: str, payload: dict[str, Any]) -> None:
    try:
        cache = Cache.get()
        client = await cache._client()
        if client:
            await client.publish(channel, json.dumps(payload, ensure_ascii=False))
            return
    except Exception as exc:
        log.debug("event_bus_publish_failed", channel=channel, error=str(exc)[:120])
    await _fanout_local(channel, payload)


async def subscribe_channel(
    channel: str,
    *,
    keepalive_sec: float = 15.0,
) -> AsyncIterator[dict[str, Any]]:
    """Async iterator of decoded pub/sub payloads with keepalive timeouts."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
    pubsub = None
    redis_task: asyncio.Task[None] | None = None

    async with _mem_lock:
        _mem_subscribers[channel].append(queue)

    try:
        cache = Cache.get()
        client = await cache._client()
        if client:
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)

            async def _redis_reader() -> None:
                assert pubsub is not None
                try:
                    while True:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=keepalive_sec,
                        )
                        if message is None:
                            continue
                        data = message.get("data")
                        if not data:
                            continue
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        if isinstance(data, str):
                            try:
                                parsed = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(parsed, dict):
                                _enqueue_with_backpressure(queue, parsed, channel=channel)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.debug("event_bus_subscribe_failed", channel=channel, error=str(exc)[:120])

            redis_task = asyncio.create_task(_redis_reader())

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=keepalive_sec)
            except asyncio.TimeoutError:
                yield {"__keepalive__": True}
                continue
            yield item
    finally:
        async with _mem_lock:
            subs = _mem_subscribers.get(channel, [])
            if queue in subs:
                subs.remove(queue)
        if redis_task is not None:
            redis_task.cancel()
            try:
                await redis_task
            except asyncio.CancelledError:
                pass
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass
