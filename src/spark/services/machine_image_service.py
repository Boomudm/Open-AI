from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from spark.core.config import settings
from spark.storage import get_storage
from spark.storage.keys import key_to_local_path, machine_image_object_key

MAX_MACHINE_IMAGE_BYTES = 2 * 1024 * 1024


def machine_image_object_path(factory_id: str, machine_id: str, mime: str) -> Path:
    key = machine_image_object_key(factory_id=factory_id, machine_id=machine_id, mime=mime)
    return key_to_local_path(
        key,
        documents_dir=settings.documents_dir,
        machines_dir=settings.machines_dir,
        feedback_dir=settings.feedback_dir,
    )


async def save_machine_image(
    *,
    factory_id: str,
    machine_id: str,
    mime: str,
    stream: BinaryIO,
    old_storage_uri: str | None = None,
) -> str:
    storage = get_storage()
    if old_storage_uri:
        try:
            await storage.delete(old_storage_uri)
        except (ValueError, OSError):
            pass
    key = machine_image_object_key(factory_id=factory_id, machine_id=machine_id, mime=mime)
    return await storage.put_object(key, stream, content_type=mime)


async def delete_machine_image(storage_uri: str | None, *, factory_id: str, machine_id: str) -> None:
    storage = get_storage()
    if storage_uri:
        try:
            await storage.delete(storage_uri)
            return
        except (ValueError, OSError):
            pass
    folder = settings.machines_dir / factory_id / machine_id
    if folder.is_dir():
        for path in folder.glob("cover.*"):
            path.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
