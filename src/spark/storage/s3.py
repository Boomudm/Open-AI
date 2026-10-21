from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

from spark.core.config import Settings, settings
from spark.storage.keys import document_object_key
from spark.storage.temp import ingest_temp_dir
from spark.storage.uri import build_s3_uri, is_s3_uri, parse_s3_uri

TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=10 * 1024 * 1024,
    multipart_chunksize=8 * 1024 * 1024,
    max_concurrency=4,
)


class S3StorageBackend:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        self.bucket = bucket
        client_kwargs: dict[str, object] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
            "config": Config(s3={"addressing_style": "path"}),
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self._client = boto3.client("s3", **client_kwargs)

    async def put_object(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        extra_args: dict[str, str] = {
            "ContentType": content_type or "application/octet-stream",
        }
        if metadata:
            extra_args["Metadata"] = {k.lower(): str(v) for k, v in metadata.items()}
        await asyncio.to_thread(
            self._client.upload_fileobj,
            stream,
            self.bucket,
            key,
            ExtraArgs=extra_args,
            Config=TRANSFER_CONFIG,
        )
        return build_s3_uri(self.bucket, key)

    async def save_document(
        self,
        doc_id: UUID,
        filename: str,
        stream: BinaryIO,
        *,
        factory_id: str,
        document_type: str,
        machine_id: str | None,
        content_type: str | None = None,
    ) -> str:
        key = document_object_key(
            factory_id=factory_id,
            document_type=document_type,
            machine_id=machine_id,
            doc_id=doc_id,
            filename=filename,
        )
        return await self.put_object(
            key,
            stream,
            content_type=content_type,
            metadata={
                "doc-id": str(doc_id),
                "factory-id": factory_id,
                "document-type": document_type,
            },
        )

    def open_sync(self, storage_uri: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        bucket, key = parse_s3_uri(storage_uri)
        response = self._client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    async def delete(self, storage_uri: str) -> None:
        bucket, key = parse_s3_uri(storage_uri)
        await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)

    async def exists(self, storage_uri: str) -> bool:
        if not is_s3_uri(storage_uri):
            return False
        bucket, key = parse_s3_uri(storage_uri)

        def _head() -> bool:
            try:
                self._client.head_object(Bucket=bucket, Key=key)
                return True
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise

        return await asyncio.to_thread(_head)

    def local_path(self, storage_uri: str) -> Path | None:
        del storage_uri
        return None

    @contextmanager
    def materialize_local(self, storage_uri: str) -> Iterator[Path]:
        bucket, key = parse_s3_uri(storage_uri)
        suffix = Path(key).suffix or ".bin"
        temp_path = ingest_temp_dir() / f"{uuid.uuid4()}{suffix}"
        try:
            with temp_path.open("wb") as out:
                self._client.download_fileobj(bucket, key, out)
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)

    def check_health(self) -> dict[str, object]:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return {"ok": True, "backend": "s3", "bucket": self.bucket}
        except Exception as exc:
            return {"ok": False, "backend": "s3", "bucket": self.bucket, "error": str(exc)[:120]}


def build_s3_backend(cfg: Settings | None = None) -> S3StorageBackend:
    cfg = cfg or settings
    endpoint = (cfg.s3_endpoint_url or "").strip()
    access_key = (cfg.s3_access_key or "").strip()
    secret_key = (cfg.s3_secret_key or "").strip()
    if not access_key or not secret_key:
        raise RuntimeError("STORAGE_BACKEND=s3 requires S3_ACCESS_KEY and S3_SECRET_KEY")
    if cfg is settings and not endpoint:
        raise RuntimeError("STORAGE_BACKEND=s3 requires S3_ENDPOINT_URL")
    return S3StorageBackend(
        endpoint_url=endpoint,
        bucket=cfg.s3_bucket,
        access_key=access_key,
        secret_key=secret_key,
        region=cfg.s3_region,
    )
