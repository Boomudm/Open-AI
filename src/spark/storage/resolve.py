from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from spark.storage import get_storage
from spark.storage.local import build_local_backend
from spark.storage.streaming import iter_sync_bytes
from spark.storage.uri import is_file_uri


async def storage_object_exists_async(storage_uri: str) -> bool:
    """Check object availability; file:// always uses local disk backend."""
    if is_file_uri(storage_uri):
        return await build_local_backend().exists(storage_uri)
    return await get_storage().exists(storage_uri)


def open_storage_object_sync(storage_uri: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
    """Stream bytes; file:// reads from disk even when STORAGE_BACKEND=s3."""
    if is_file_uri(storage_uri):
        return build_local_backend().open_sync(storage_uri, chunk_size=chunk_size)
    return get_storage().open_sync(storage_uri, chunk_size=chunk_size)


async def open_storage_object_async(
    storage_uri: str, chunk_size: int = 1 << 20
) -> AsyncIterator[bytes]:
    """Non-blocking async byte stream for FastAPI StreamingResponse."""
    sync_iter = open_storage_object_sync(storage_uri, chunk_size=chunk_size)
    async for chunk in iter_sync_bytes(sync_iter):
        yield chunk
