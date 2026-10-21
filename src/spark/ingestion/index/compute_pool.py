"""Dedicated thread pool for index-time dense + sparse encoding (Phase 5)."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from qdrant_client.models import SparseVector

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import ingest_compute_pool_queue_depth
from spark.ingestion.index.batch_encode import encode_dense_sync, encode_sparse_sync_batch
from spark.ingestion.index.embed_retry import with_embed_retry

log = get_logger(__name__)

_executor: ThreadPoolExecutor | None = None
_pending_encode_jobs = 0


def _adjust_queue_depth(delta: int) -> None:
    global _pending_encode_jobs
    _pending_encode_jobs = max(0, _pending_encode_jobs + delta)
    ingest_compute_pool_queue_depth.set(_pending_encode_jobs)


def _pool_workers() -> int:
    configured = int(getattr(settings, "ingest_encode_workers", 0) or 0)
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2) // 2)


def get_ingest_executor() -> ThreadPoolExecutor:
    """Singleton executor shared by dense and sparse batch jobs in this process."""
    global _executor
    if _executor is None:
        workers = _pool_workers()
        _executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ingest-encode")
        log.info("ingest_compute_pool_started", workers=workers)
    return _executor


def shutdown_ingest_executor() -> None:
    """Release pool threads (tests / graceful shutdown)."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


class IngestComputePool:
    """Batch-oriented encode API — never runs model code on the event loop thread."""

    _instance: IngestComputePool | None = None

    @classmethod
    def get(cls) -> IngestComputePool:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        cls._instance = None
        shutdown_ingest_executor()

    async def encode_dense_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        executor = get_ingest_executor()

        async def _run() -> list[list[float]]:
            _adjust_queue_depth(1)
            try:
                return await loop.run_in_executor(executor, encode_dense_sync, texts)
            finally:
                _adjust_queue_depth(-1)

        return await with_embed_retry(_run)

    async def encode_sparse_batch(self, texts: list[str]) -> list[SparseVector]:
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        executor = get_ingest_executor()

        async def _run() -> list[SparseVector]:
            _adjust_queue_depth(1)
            try:
                return await loop.run_in_executor(executor, encode_sparse_sync_batch, texts)
            finally:
                _adjust_queue_depth(-1)

        return await with_embed_retry(_run)
