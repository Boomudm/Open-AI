from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest

from spark.storage.local import LocalStorageBackend
from spark.storage.uri import build_file_uri, is_file_uri


@pytest.mark.asyncio
async def test_local_storage_round_trip(tmp_path: Path) -> None:
    backend = LocalStorageBackend(
        documents_dir=tmp_path / "documents",
        machines_dir=tmp_path / "machines",
        feedback_dir=tmp_path / "feedback",
    )
    doc_id = uuid.uuid4()
    data = b"%PDF-1.4 test content"
    uri = await backend.save_document(
        doc_id,
        "manual.pdf",
        io.BytesIO(data),
        factory_id="F-01",
        document_type="machine_manual",
        machine_id="MC-001",
        content_type="application/pdf",
    )
    assert is_file_uri(uri)
    assert await backend.exists(uri)
    chunks = list(backend.open_sync(uri))
    assert b"".join(chunks) == data
    local = backend.local_path(uri)
    assert local is not None and local.is_file()
    await backend.delete(uri)
    assert not await backend.exists(uri)


@pytest.mark.asyncio
async def test_local_storage_legacy_file_uri(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.pdf"
    legacy.write_bytes(b"legacy")
    uri = build_file_uri(legacy)
    backend = LocalStorageBackend(
        documents_dir=tmp_path / "documents",
        machines_dir=tmp_path / "machines",
        feedback_dir=tmp_path / "feedback",
    )
    assert await backend.exists(uri)
    assert b"".join(backend.open_sync(uri)) == b"legacy"
