"""Detect deprecated env/config usage at startup (Phase 13 teardown)."""

from __future__ import annotations

import os

from spark.core.logging import get_logger
from spark.core.metrics import deprecated_config_usage_total

log = get_logger(__name__)

_DEPRECATED_ENV_KEYS: tuple[tuple[str, str], ...] = (
    ("RAGFLOW_API_URL", "RAGFlow integration removed — use native ingest only"),
    ("RAGFLOW_API_KEY", "RAGFlow integration removed — use native ingest only"),
    ("RAGFLOW_DATASET_ID", "RAGFlow integration removed — use native ingest only"),
    ("RERANKER_STRATEGY", "Cross-encoder rerank is always on — set RERANKER_MODEL instead"),
    ("RAG_HYBRID_RETRIEVAL_ENABLED", "Hybrid retrieval is always on — remove this flag"),
)

_DEPRECATED_INGEST_BACKENDS = frozenset({"ragflow", "auto"})


def audit_deprecated_config() -> None:
    """Log warnings and increment metrics when legacy env vars are still set."""
    for key, message in _DEPRECATED_ENV_KEYS:
        if os.environ.get(key, "").strip():
            deprecated_config_usage_total.labels(key=key).inc()
            log.warning("deprecated_config_usage", key=key, message=message)

    requested = os.environ.get("INGEST_BACKEND", "native").strip().lower()
    if requested in _DEPRECATED_INGEST_BACKENDS:
        deprecated_config_usage_total.labels(key="INGEST_BACKEND").inc()
        log.warning(
            "ingest_backend_deprecated",
            requested=requested,
            effective="native",
            message="Only native ingest is supported",
        )
