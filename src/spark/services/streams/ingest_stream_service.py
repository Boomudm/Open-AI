"""Ingest job progress SSE via Redis pub/sub (app-layer Phase 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from spark.core.event_bus import ingest_job_channel
from spark.core.logging import get_logger
from spark.services.ingest_progress import ingest_progress_emitter
from spark.services.streams.redis_bus import redis_stream_bus
from spark.services.streams.sse_frame import sse_comment, sse_data, sse_event

log = get_logger(__name__)

_TERMINAL = {"completed", "partial", "failed", "dlq", "pending_release"}


def _is_terminal(payload: dict) -> bool:
    status = str(payload.get("status") or payload.get("stage") or "").lower()
    return status in _TERMINAL


class IngestStreamService:
    async def stream_job(self, job_id: UUID) -> AsyncIterator[str]:
        job_key = str(job_id)
        channel = ingest_job_channel(job_key)
        yield sse_event("connected", {})

        latest = await ingest_progress_emitter.get_latest(job_key)
        if latest:
            yield sse_data(latest)
            if _is_terminal(latest):
                return

        try:
            async for raw in redis_stream_bus.subscribe(channel, keepalive_sec=15.0):
                if raw.get("__keepalive__"):
                    yield sse_comment("keepalive")
                    continue
                if str(raw.get("job_id") or "") not in ("", job_key):
                    continue
                yield sse_data(raw)
                if _is_terminal(raw):
                    return
        except Exception as exc:
            log.warning("ingest_stream_subscribe_failed", job_id=job_key, error=str(exc)[:200])
            yield sse_event("error", {"message": "stream failed"})


ingest_stream_service = IngestStreamService()
