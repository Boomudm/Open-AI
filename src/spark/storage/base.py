from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID


class StorageBackend(Protocol):
    async def put_object(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Persist bytes at object key; return storage_uri (file:// or s3://)."""

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
        """Persist ingested document; return storage_uri."""

    def open_sync(self, storage_uri: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """Yield file chunks for streaming responses."""

    async def delete(self, storage_uri: str) -> None:
        """Remove stored object."""

    async def exists(self, storage_uri: str) -> bool:
        """Return whether the object is present."""

    def local_path(self, storage_uri: str) -> Path | None:
        """Return local filesystem path when available (ingest workers)."""

    @contextmanager
    def materialize_local(self, storage_uri: str) -> Iterator[Path]:
        """Yield a local path for reading; remove temp files on exit when downloaded."""
