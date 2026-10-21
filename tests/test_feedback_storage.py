"""Feedback photo storage helpers."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uuid

from spark.core.config import settings
from spark.services.feedback_service import (
    delete_feedback_files,
    feedback_photo_path,
    save_feedback_photo,
)
from spark.storage import get_storage


@pytest.mark.asyncio
async def test_save_and_delete_feedback_photo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "documents_dir", tmp_path / "documents")
    monkeypatch.setattr(settings, "machines_dir", tmp_path / "machines")
    monkeypatch.setattr(settings, "feedback_dir", tmp_path / "feedback")
    get_storage.cache_clear()

    fid = uuid.uuid4()
    created_at = datetime(2026, 6, 15, tzinfo=UTC)
    uri = await save_feedback_photo(
        factory_id="F-01",
        feedback_id=fid,
        created_at=created_at,
        sort_order=0,
        mime="image/jpeg",
        stream=io.BytesIO(b"\xff\xd8\xff"),
    )
    assert uri.startswith("file://")
    path = feedback_photo_path(
        factory_id="F-01",
        feedback_id=fid,
        created_at=created_at,
        sort_order=0,
        mime="image/jpeg",
    )
    assert path.is_file()
    await delete_feedback_files([uri])
    assert not path.exists()
