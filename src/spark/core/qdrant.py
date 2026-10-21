from __future__ import annotations

import asyncio
from typing import Any

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PayloadSchemaType, SparseVectorParams, VectorParams

from spark.core.config import settings
from spark.core.llm_profile import embedding_dimension
from spark.core.logging import get_logger

log = get_logger(__name__)

QDRANT_OPERATION_TIMEOUT_SEC = 30
QDRANT_RETRY_ATTEMPTS = 3
QDRANT_RETRY_BASE_DELAY = 0.5


async def qdrant_retry_async(fn, *, attempts: int = QDRANT_RETRY_ATTEMPTS, timeout: float = QDRANT_OPERATION_TIMEOUT_SEC):
    """Retry an async Qdrant operation with exponential backoff and timeout."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout)
        except asyncio.TimeoutError:
            last_exc = TimeoutError(f"Qdrant operation timed out after {timeout}s")
            log.warning("qdrant_timeout", attempt=attempt + 1, timeout=timeout)
        except (ConnectionError, OSError, UnexpectedResponse) as exc:
            last_exc = exc
            log.warning("qdrant_retry", attempt=attempt + 1, error=str(exc)[:200])
        except Exception as exc:
            exc_name = type(exc).__name__
            if exc_name not in {"ConnectError", "ResponseHandlingException", "RemoteProtocolError"}:
                raise
            last_exc = exc
            log.warning("qdrant_retry", attempt=attempt + 1, error=str(exc)[:200])
        if attempt < attempts - 1:
            delay = QDRANT_RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
    raise last_exc or RuntimeError("qdrant_retry exhausted")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

INDEXED_FIELDS: list[tuple[str, PayloadSchemaType]] = [
    ("doc_id", PayloadSchemaType.KEYWORD),
    ("chunk_id", PayloadSchemaType.KEYWORD),
    ("machine_id", PayloadSchemaType.KEYWORD),
    ("factory_id", PayloadSchemaType.KEYWORD),
    ("component_id", PayloadSchemaType.KEYWORD),
    ("document_category", PayloadSchemaType.KEYWORD),
    ("document_type", PayloadSchemaType.KEYWORD),
    ("revision", PayloadSchemaType.KEYWORD),
    ("language", PayloadSchemaType.KEYWORD),
    ("ingest_version", PayloadSchemaType.KEYWORD),
    ("ingest_generation", PayloadSchemaType.INTEGER),
    ("embed_model_version", PayloadSchemaType.KEYWORD),
    ("retrieval_enabled", PayloadSchemaType.BOOL),
    ("chunk_index", PayloadSchemaType.INTEGER),
    ("page", PayloadSchemaType.INTEGER),
    ("effective_date", PayloadSchemaType.INTEGER),
    ("expiry_date", PayloadSchemaType.INTEGER),
    ("ingested_at", PayloadSchemaType.INTEGER),
    ("sensitivity_level", PayloadSchemaType.KEYWORD),
]


def sparse_vectors_enabled() -> bool:
    """Sparse vectors on by default; test profile may disable for speed."""
    if settings.spark_profile == "test" and settings.sparse_vectors_disabled:
        return False
    return True


_sync_client: QdrantClient | None = None
_async_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _sync_client
    if _sync_client is None:
        _sync_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=QDRANT_OPERATION_TIMEOUT_SEC,
        )
    return _sync_client


def get_async_qdrant_client() -> AsyncQdrantClient:
    global _async_client
    if _async_client is None:
        _async_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=QDRANT_OPERATION_TIMEOUT_SEC,
        )
    return _async_client


async def close_qdrant_clients() -> None:
    """Close and clear both cached clients (app shutdown).

    Clearing the globals matters: closing without resetting leaves every later
    caller (a second app lifecycle in tests, a worker warm restart) holding a
    dead client that raises "Cannot send a request, as the client has been
    closed" instead of reconnecting.
    """
    global _sync_client, _async_client
    if _async_client is not None:
        try:
            await _async_client.close()
        except Exception as exc:
            log.warning("qdrant_async_close_failed", error=str(exc)[:200])
        _async_client = None
    if _sync_client is not None:
        try:
            _sync_client.close()
        except Exception as exc:
            log.warning("qdrant_sync_close_failed", error=str(exc)[:200])
        _sync_client = None


def reset_async_qdrant_client() -> None:
    """Drop the cached async client so the next call opens a fresh one.

    AsyncQdrantClient wraps an httpx connection pool bound to whichever asyncio
    event loop was active when it was created. In Celery workers, each task runs
    its own asyncio.run() (its own event loop), so a client cached across tasks
    ends up reusing connections tied to an already-closed loop, raising
    'RuntimeError: Event loop is closed' on the next Qdrant call. Call this from
    a task_postrun hook (see spark.workers.celery_app) to force a fresh client
    per task, same fix as the SQLAlchemy engine pool reset.
    """
    global _async_client
    _async_client = None


def _existing_dense_dim(info: Any) -> int | None:
    vectors = getattr(info.config.params, "vectors", None)
    if vectors is None:
        return None
    if isinstance(vectors, dict):
        dense = vectors.get(DENSE_VECTOR_NAME)
        return int(dense.size) if dense is not None else None
    return int(vectors.size)  # type: ignore[union-attr]


_ensured_collections: set[str] = set()


def ensure_collection(collection: str | None = None, vector_size: int | None = None) -> None:
    """Create collection v2 (named dense + sparse) + payload indexes. Idempotent.

    Called once per batch from QdrantWriter.write() — a large document can mean
    dozens of batches, and every call re-issued ~20 create_payload_index HTTP
    round-trips that Qdrant just rejects as already-existing. Collection schema
    doesn't change mid-process, so memoize per collection name to skip the
    redundant work after the first successful ensure.
    """
    coll = collection or settings.qdrant_collection
    if coll in _ensured_collections:
        return
    client = get_qdrant_client()
    dim = vector_size or embedding_dimension()
    sparse_on = sparse_vectors_enabled()

    vectors_config = {DENSE_VECTOR_NAME: VectorParams(size=dim, distance=Distance.COSINE)}
    sparse_config = {SPARSE_VECTOR_NAME: SparseVectorParams()} if sparse_on else None

    try:
        info = client.get_collection(coll)
    except (UnexpectedResponse, ValueError):
        info = None

    if info is not None:
        existing_dim = _existing_dense_dim(info)
        if existing_dim is not None and existing_dim != dim:
            raise RuntimeError(
                f"Qdrant collection {coll!r} dense vector size is {existing_dim}, "
                f"but active embedding size is {dim}. Reindex or use a matching profile."
            )
        if sparse_on:
            sparse_cfg = getattr(info.config.params, "sparse_vectors", None) or {}
            if SPARSE_VECTOR_NAME not in sparse_cfg:
                log.info("qdrant_sparse_vector_enable", collection=coll)
                try:
                    client.update_collection(
                        collection_name=coll,
                        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
                    )
                except Exception as exc:
                    log.warning("qdrant_sparse_vector_enable_failed", collection=coll, error=str(exc)[:200])
    else:
        log.info(
            "qdrant_collection_create",
            collection=coll,
            dim=dim,
            sparse=sparse_on,
            schema="v2_named_vectors",
        )
        kwargs: dict[str, Any] = {
            "collection_name": coll,
            "vectors_config": vectors_config,
            "on_disk_payload": True,
        }
        if sparse_config:
            kwargs["sparse_vectors_config"] = sparse_config
        try:
            client.create_collection(**kwargs)
        except UnexpectedResponse as exc:
            if exc.status_code != 409:
                raise
            log.debug("qdrant_collection_already_exists", collection=coll)

    for field, schema in INDEXED_FIELDS:
        try:
            client.create_payload_index(
                collection_name=coll,
                field_name=field,
                field_schema=schema,
            )
            log.info("qdrant_payload_index_created", field=field)
        except Exception as exc:
            log.debug("qdrant_payload_index_skip", field=field, reason=str(exc)[:120])

    _ensured_collections.add(coll)


def ensure_enterprise_collection(collection: str | None = None, vector_size: int | None = None) -> None:
    """Create enterprise collection (dense + sparse when enabled) + payload indexes. Idempotent."""
    client = get_qdrant_client()
    coll = collection or settings.qdrant_enterprise_collection
    dim = vector_size or embedding_dimension()
    sparse_on = sparse_vectors_enabled()

    vectors_config = {DENSE_VECTOR_NAME: VectorParams(size=dim, distance=Distance.COSINE)}
    sparse_config = {SPARSE_VECTOR_NAME: SparseVectorParams()} if sparse_on else None

    try:
        info = client.get_collection(coll)
    except (UnexpectedResponse, ValueError):
        info = None

    if info is not None:
        existing_dim = _existing_dense_dim(info)
        if existing_dim is not None and existing_dim != dim:
            raise RuntimeError(
                f"Qdrant enterprise collection {coll!r} dense vector size is {existing_dim}, "
                f"but active embedding size is {dim}. Reindex or use a matching profile."
            )
        if sparse_on:
            sparse_cfg = getattr(info.config.params, "sparse_vectors", None) or {}
            if SPARSE_VECTOR_NAME not in sparse_cfg:
                log.info("qdrant_enterprise_sparse_vector_enable", collection=coll)
                try:
                    client.update_collection(
                        collection_name=coll,
                        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
                    )
                except Exception as exc:
                    log.warning("qdrant_enterprise_sparse_vector_enable_failed", collection=coll, error=str(exc)[:200])
    else:
        log.info(
            "qdrant_enterprise_collection_create",
            collection=coll,
            dim=dim,
            sparse=sparse_on,
        )
        kwargs: dict[str, Any] = {
            "collection_name": coll,
            "vectors_config": vectors_config,
            "on_disk_payload": True,
        }
        if sparse_config:
            kwargs["sparse_vectors_config"] = sparse_config
        try:
            client.create_collection(**kwargs)
        except UnexpectedResponse as exc:
            if exc.status_code != 409:
                raise
            log.debug("qdrant_enterprise_collection_already_exists", collection=coll)

    for field, schema in INDEXED_FIELDS:
        try:
            client.create_payload_index(
                collection_name=coll,
                field_name=field,
                field_schema=schema,
            )
        except Exception as exc:
            log.debug("qdrant_enterprise_payload_index_skip", field=field, reason=str(exc)[:120])


def recreate_collection(collection: str, *, vector_size: int | None = None) -> None:
    """Drop and recreate a collection with schema v2 (pre-production only)."""
    client = get_qdrant_client()
    dim = vector_size or embedding_dimension()
    sparse_on = sparse_vectors_enabled()
    _ensured_collections.discard(collection)
    try:
        client.delete_collection(collection_name=collection)
        log.info("qdrant_collection_dropped", collection=collection)
    except Exception as exc:
        log.debug("qdrant_collection_drop_skip", collection=collection, reason=str(exc)[:120])
    kwargs: dict[str, Any] = {
        "collection_name": collection,
        "vectors_config": {DENSE_VECTOR_NAME: VectorParams(size=dim, distance=Distance.COSINE)},
        "on_disk_payload": True,
    }
    if sparse_on:
        kwargs["sparse_vectors_config"] = {SPARSE_VECTOR_NAME: SparseVectorParams()}
    client.create_collection(**kwargs)
    for field, schema in INDEXED_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            pass
    log.info("qdrant_collection_recreated", collection=collection, dim=dim, sparse=sparse_on)
