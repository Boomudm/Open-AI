from __future__ import annotations

from functools import lru_cache

from spark.core.config import settings
from spark.storage.base import StorageBackend
from spark.storage.local import build_local_backend
from spark.storage.s3 import S3StorageBackend, build_s3_backend


@lru_cache
def get_storage() -> StorageBackend:
    backend = (settings.storage_backend or "local").lower()
    if backend == "s3":
        return build_s3_backend()
    return build_local_backend()


def check_storage_health() -> dict[str, object]:
    backend = (settings.storage_backend or "local").lower()
    if backend == "s3":
        storage = get_storage()
        if isinstance(storage, S3StorageBackend):
            return storage.check_health()
        return {"ok": False, "backend": "s3", "error": "unexpected storage backend type"}

    documents_dir = settings.documents_dir.expanduser().resolve()
    try:
        documents_dir.mkdir(parents=True, exist_ok=True)
        probe = documents_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "backend": "local", "path": str(documents_dir)}
    except OSError as exc:
        return {"ok": False, "backend": "local", "path": str(documents_dir), "error": str(exc)[:120]}


__all__ = ["StorageBackend", "get_storage", "check_storage_health"]
