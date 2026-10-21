"""Tests for ingest retry classification, alias warn, and Celery policy."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from spark.ingestion.errors import (
    PermanentIngestError,
    TransientIngestError,
    classify_pipeline_exception,
)
from spark.ingestion.stages.common import apply_alias_resolution as _apply_alias_resolution
from spark.ingestion.parsers.base import ParsedRecord
from spark.services.ingest_rate_limit import check_single_file_rate_limit
from spark.workers import tasks as worker_tasks


def test_classify_qdrant_timeout_as_transient() -> None:
    exc = classify_pipeline_exception(httpx.TimeoutException("timed out"))
    assert isinstance(exc, TransientIngestError)
    assert exc.reason_code == "qdrant_timeout"


def test_classify_config_error_as_permanent() -> None:
    from spark.ingestion.config_resolver import ConfigError

    exc = classify_pipeline_exception(ConfigError("missing profile"))
    assert isinstance(exc, PermanentIngestError)
    assert exc.reason_code == "config_profile_not_found"


def test_classify_oom_as_transient() -> None:
    exc = classify_pipeline_exception(RuntimeError("CUDA out of memory"))
    assert isinstance(exc, TransientIngestError)
    assert exc.reason_code == "embed_transient"


def test_ingest_task_has_autoretry_policy() -> None:
    task = worker_tasks.ingest_document_task
    assert TransientIngestError in task.autoretry_for
    assert task.max_retries == 5
    assert task.acks_late is True
    assert task.retry_backoff is True


@pytest.mark.asyncio
async def test_alias_on_fail_warn_proceeds() -> None:
    resolver = MagicMock()
    resolver.resolve_machine = AsyncMock(return_value=None)
    session = MagicMock()
    rec = ParsedRecord(
        route="both",
        payload={"machine_label": "unknown-machine", "row_number": 2},
        text_for_embedding="text",
    )
    config = {
        "resolve_aliases": [
            {
                "field": "machine_label",
                "via": "machine_alias_resolver",
                "target": "machine_id",
                "on_fail": "warn",
            }
        ]
    }
    ok, reason, detail = await _apply_alias_resolution(
        rec, config, resolver, session, job_id=uuid.uuid4()
    )
    assert ok is True
    assert reason is None
    assert rec.payload["machine_label_unresolved"] == "unknown-machine"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_single_file_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from spark.core.cache import Cache

    class FakeCache:
        async def get_json(self, _key: str):
            return {"count": 60}

        async def set_json(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(Cache, "get", lambda: FakeCache())
    monkeypatch.setattr(
        "spark.services.ingest_rate_limit.settings.ingest_single_file_rate_limit_per_hour",
        60,
    )

    with pytest.raises(HTTPException) as exc:
        await check_single_file_rate_limit("F-01")
    assert exc.value.status_code == 429
