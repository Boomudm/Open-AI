"""Batch sizing and concurrency policy for index writers."""

from __future__ import annotations

from spark.core.config import settings

DEFAULT_EMBED_BATCH_SIZE = 32
DEFAULT_UPSERT_CONCURRENCY = 1


def embed_batch_size() -> int:
    return max(1, int(getattr(settings, "ingest_embed_batch_size", DEFAULT_EMBED_BATCH_SIZE)))


def upsert_concurrency() -> int:
    return max(1, int(getattr(settings, "ingest_upsert_concurrency", DEFAULT_UPSERT_CONCURRENCY)))
