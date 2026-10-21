"""Ingest job progress events for SSE and notifications."""

from __future__ import annotations

from typing import Any

from spark.core.cache import Cache
from spark.core.event_bus import INGEST_CHANNEL, ingest_job_channel, publish_event
from spark.core.logging import get_logger

log = get_logger(__name__)

_PROGRESS_TTL_SEC = 86_400


def _progress_key(job_id: str) -> str:
    return f"ingest:progress:{job_id}"


class IngestProgressEmitter:
    async def emit(
        self,
        *,
        job_id: str,
        factory_id: str | None,
        percent: int,
        rows_ok: int,
        rows_total: int,
        stage: str,
        status: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "job_id": job_id,
            "factory_id": factory_id,
            "percent": max(0, min(100, int(percent))),
            "rows_ok": int(rows_ok),
            "rows_total": int(rows_total),
            "stage": stage,
        }
        if status:
            payload["status"] = status
        try:
            cache = Cache.get()
            await cache.set_json(_progress_key(job_id), payload, ttl=_PROGRESS_TTL_SEC)
        except Exception as exc:
            log.debug("ingest_progress_cache_failed", job_id=job_id, error=str(exc)[:120])
        await publish_event(INGEST_CHANNEL, payload)
        await publish_event(ingest_job_channel(job_id), payload)

    async def get_latest(self, job_id: str) -> dict[str, Any] | None:
        try:
            cache = Cache.get()
            data = await cache.get_json(_progress_key(job_id))
            return data if isinstance(data, dict) else None
        except Exception:
            return None


ingest_progress_emitter = IngestProgressEmitter()
