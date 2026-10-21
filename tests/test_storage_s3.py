"""S3/MinIO storage backend tests (moto mock).

For multipart behaviour with real MinIO, upload a ~50MB PDF locally once via
docker compose dev overlay — not required in CI.
"""

from __future__ import annotations

import io
import os
import time
import uuid
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from spark.core.config import Settings
from spark.storage.s3 import build_s3_backend
from spark.storage.temp import cleanup_stale_ingest_temp, ingest_temp_dir
from spark.storage.uri import is_s3_uri, parse_s3_uri


@pytest.fixture
def s3_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr("spark.storage.temp.settings.ingest_temp_dir", tmp_path / "ingest-temp")
    monkeypatch.setattr("spark.storage.temp.settings.ingest_temp_ttl_seconds", 1)
    return Settings(
        storage_backend="s3",
        s3_endpoint_url="",
        s3_bucket="spark-documents",
        s3_access_key="testing",
        s3_secret_key="testing",
        s3_region="us-east-1",
        ingest_temp_dir=tmp_path / "ingest-temp",
        ingest_temp_ttl_seconds=1,
    )


@pytest.mark.asyncio
async def test_s3_storage_round_trip(s3_settings: Settings) -> None:
    with mock_aws():
        client = boto3.client("s3", region_name=s3_settings.s3_region)
        client.create_bucket(Bucket=s3_settings.s3_bucket)

        backend = build_s3_backend(s3_settings)
        doc_id = uuid.uuid4()
        data = b"%PDF-1.4 s3 test"
        uri = await backend.save_document(
            doc_id,
            "manual.pdf",
            io.BytesIO(data),
            factory_id="F-01",
            document_type="machine_manual",
            machine_id="MC-001",
            content_type="application/pdf",
        )
        assert is_s3_uri(uri)
        bucket, key = parse_s3_uri(uri)
        assert bucket == s3_settings.s3_bucket
        assert key.startswith("documents/F-01/machine_manual/MC-001/")
        assert await backend.exists(uri)
        assert b"".join(backend.open_sync(uri)) == data

        head = client.head_object(Bucket=bucket, Key=key)
        assert head["ContentType"] == "application/pdf"

        with backend.materialize_local(uri) as path:
            assert path.is_file()
            assert path.read_bytes() == data
        assert not path.exists()

        await backend.delete(uri)
        assert not await backend.exists(uri)


@pytest.mark.asyncio
async def test_cleanup_stale_ingest_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark.storage.temp.settings.ingest_temp_dir", tmp_path / "ingest-temp")
    monkeypatch.setattr("spark.storage.temp.settings.ingest_temp_ttl_seconds", 1)

    temp_dir = ingest_temp_dir()
    stale = temp_dir / "stale.tmp"
    stale.write_bytes(b"old")
    old_mtime = time.time() - 120
    os.utime(stale, (old_mtime, old_mtime))

    removed = cleanup_stale_ingest_temp(max_age_seconds=30)
    assert removed == 1
    assert not stale.exists()

    fresh = temp_dir / "fresh.tmp"
    fresh.write_bytes(b"new")
    assert cleanup_stale_ingest_temp(max_age_seconds=30) == 0
    assert fresh.exists()
