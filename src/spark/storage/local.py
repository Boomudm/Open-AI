from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from spark.core.config import Settings, settings
from spark.storage.keys import document_object_key, key_to_local_path
from spark.storage.uri import build_file_uri, is_file_uri, parse_file_uri


class LocalStorageBackend:
    def __init__(
        self,
        *,
        documents_dir: Path | None = None,
        machines_dir: Path | None = None,
        profile_images_dir: Path | None = None,
        feedback_dir: Path | None = None,
        chat_attachments_dir: Path | None = None,
    ) -> None:
        self.documents_dir = (documents_dir or settings.documents_dir).resolve()
        self.machines_dir = (machines_dir or settings.machines_dir).resolve()
        self.profile_images_dir = (profile_images_dir or settings.profile_images_dir).resolve()
        self.feedback_dir = (feedback_dir or settings.feedback_dir).resolve()
        self.chat_attachments_dir = (chat_attachments_dir or settings.chat_attachments_dir).resolve()
        # Directories are created lazily in put_object(). Creating all four
        # eagerly here breaks every construction (including tests and read-only
        # callers) whenever a single unused root is on an unwritable mount.

    def _path_for_key(self, key: str) -> Path:
        return key_to_local_path(
            key,
            documents_dir=self.documents_dir,
            machines_dir=self.machines_dir,
            feedback_dir=self.feedback_dir,
            profile_images_dir=self.profile_images_dir,
            chat_attachments_dir=self.chat_attachments_dir,
        )

    async def put_object(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        del content_type, metadata
        target = self._path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            shutil.copyfileobj(stream, out)
        return build_file_uri(target)

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
        return await self.put_object(key, stream, content_type=content_type)

    def open_sync(self, storage_uri: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        path = self._resolve_path(storage_uri)
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def delete(self, storage_uri: str) -> None:
        path = self._resolve_path(storage_uri)
        if path.is_file():
            path.unlink()
        parent = path.parent
        while parent not in (
            self.documents_dir,
            self.machines_dir,
            self.profile_images_dir,
            self.feedback_dir,
            self.chat_attachments_dir,
        ):
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break

    async def exists(self, storage_uri: str) -> bool:
        try:
            return self._resolve_path(storage_uri).is_file()
        except (ValueError, OSError):
            return False

    def local_path(self, storage_uri: str) -> Path | None:
        if not is_file_uri(storage_uri):
            return None
        try:
            return self._resolve_path(storage_uri)
        except ValueError:
            return None

    @contextmanager
    def materialize_local(self, storage_uri: str) -> Iterator[Path]:
        path = self._resolve_path(storage_uri)
        yield path

    def _resolve_path(self, storage_uri: str) -> Path:
        if not is_file_uri(storage_uri):
            raise ValueError(f"local backend cannot resolve non-file URI: {storage_uri}")
        return parse_file_uri(storage_uri)


def build_local_backend(cfg: Settings | None = None) -> LocalStorageBackend:
    cfg = cfg or settings
    return LocalStorageBackend(
        documents_dir=cfg.documents_dir,
        machines_dir=cfg.machines_dir,
        profile_images_dir=cfg.profile_images_dir,
        feedback_dir=cfg.feedback_dir,
        chat_attachments_dir=cfg.chat_attachments_dir,
    )
