"""Dispatch factory notifications for Celery beat events."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.services.factory_config_service import factory_config_service
from spark.services.notifications import build_providers

log = get_logger(__name__)


class NotificationDispatchService:
    async def notify_factory(
        self,
        db: AsyncSession,
        *,
        factory_id: str,
        event_type: str,
        subject: str,
        body: str,
        context: dict[str, Any] | None = None,
    ) -> int:
        cfg = await factory_config_service.resolve(db, factory_id)
        notify_cfg = cfg.get("notifications") or {}
        if not notify_cfg.get("enabled"):
            return 0
        if event_type == "insights_hotness" and not notify_cfg.get("insights_hotness", True):
            return 0
        if event_type == "ingest_failed" and not notify_cfg.get("ingest_failed", True):
            return 0
        if event_type == "ocr_low_confidence" and not notify_cfg.get("ocr_low_confidence", True):
            return 0
        if event_type == "vector_drift" and not notify_cfg.get("vector_drift", True):
            return 0
        providers = build_providers(list(notify_cfg.get("channels") or []))
        sent = 0
        payload = {"factory_id": factory_id, "event_type": event_type, **(context or {})}
        for provider in providers:
            if await provider.send(subject=subject, body=body, context=payload):
                sent += 1
        log.info("factory_notify_sent", factory_id=factory_id, event_type=event_type, sent=sent)
        return sent


notification_dispatch_service = NotificationDispatchService()
