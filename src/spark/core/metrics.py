"""Prometheus metrics + FastAPI middleware to record request latencies/counts.

Exposes counters/histograms used across the codebase:
- spark_http_requests_total{method, path, status}
- spark_http_request_seconds{method, path}
- spark_rag_query_seconds{intent, fallback_level}
- spark_rag_query_total{fallback_level}
- spark_rag_scope_broadened_total{fallback_level}
- spark_rag_embed_error_total
- spark_rag_doc_rerank_seconds
- spark_sql_judge_pass_total{outcome}
- spark_ingest_rows_total{document_type, outcome}
- spark_embedding_seconds
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

http_requests_total = Counter(
    "spark_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
http_request_seconds = Histogram(
    "spark_http_request_seconds",
    "HTTP request latency",
    ["method", "path"],
)
http_rate_limited_total = Counter(
    "spark_http_rate_limited_total",
    "HTTP requests rejected by global rate limit",
    ["scope", "rate_class"],
)
http_admission_rejected_total = Counter(
    "spark_http_admission_rejected_total",
    "HTTP requests rejected by admission control",
    ["plane", "reason"],
)
http_inflight_gauge = Gauge(
    "spark_http_inflight",
    "In-flight HTTP requests by admission plane",
    ["plane"],
)
sse_connections_active = Gauge(
    "spark_sse_connections_active",
    "Active SSE connections by channel",
    ["channel"],
)
sse_connections_rejected_total = Counter(
    "spark_sse_connections_rejected_total",
    "SSE connections rejected by connection governor",
    ["reason", "channel"],
)
acl_cache_miss_duration_seconds = Histogram(
    "spark_acl_cache_miss_duration_seconds",
    "ACL allowed-doc compute duration on cache miss",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
rag_query_seconds = Histogram(
    "spark_rag_query_seconds",
    "RAG query latency",
    ["intent", "fallback_level", "degraded"],
)
rag_query_total = Counter(
    "spark_rag_query_total",
    "Completed RAG queries",
    ["fallback_level"],
)
rag_scope_broadened_total = Counter(
    "spark_rag_scope_broadened_total",
    "RAG queries that broadened retrieval scope (fallback_level > 0)",
    ["fallback_level"],
)
rag_embed_error_total = Counter(
    "spark_rag_embed_error_total",
    "Vector retrieval leg embed failures",
)
rag_vector_collection_fail_total = Counter(
    "spark_rag_vector_collection_fail_total",
    "Qdrant collection search failures during RAG retrieval",
    ["collection"],
)
context_trim_total = Counter(
    "spark_context_trim_total",
    "Context budget trims applied before LLM invoke",
    ["reason"],
)
qa_cache_hit_total = Counter(
    "spark_qa_cache_hit_total",
    "Verified Q&A cache hits",
)
qa_cache_invalidate_total = Counter(
    "spark_qa_cache_invalidate_total",
    "Verified Q&A cache invalidations",
)
rag_doc_rerank_seconds = Histogram(
    "spark_rag_doc_rerank_seconds",
    "Cross-document rerank latency",
)
sql_judge_pass_total = Counter(
    "spark_sql_judge_pass_total",
    "SQL semantic validation outcomes",
    ["outcome"],
)
ingest_rows_total = Counter(
    "spark_ingest_rows_total",
    "Rows processed during ingestion",
    ["document_type", "outcome"],   # outcome = ok|skipped|failed
)
embedding_seconds = Histogram(
    "spark_embedding_seconds",
    "Embedding call latency",
)
sparse_encode_empty_total = Counter(
    "spark_sparse_encode_empty_total",
    "Sparse encode calls that produced empty index vectors",
)
rag_lexical_degraded_total = Counter(
    "spark_rag_lexical_degraded_total",
    "Lexical retrieval failures — vector-only fallback",
    ["engine", "reason"],
)
rag_circuit_open = Gauge(
    "spark_rag_circuit_open",
    "Whether a factory dependency circuit breaker is open (1=open, 0=closed)",
    ["factory_id", "dependency"],
)
rag_circuit_trip_total = Counter(
    "spark_rag_circuit_trip_total",
    "Circuit breaker trips by factory, dependency, and reason",
    ["factory_id", "dependency", "reason"],
)
circuit_outcome_dropped_total = Counter(
    "spark_circuit_outcome_dropped_total",
    "Circuit outcome recordings dropped after async failure",
    ["factory_id", "dependency", "outcome"],
)
generation_stream_pseudo_total = Counter(
    "spark_generation_stream_pseudo_total",
    "Validated pseudo-stream responses (tokens emitted after full grounding)",
)
thai_retry_extractive_fallback_total = Counter(
    "spark_thai_retry_extractive_fallback_total",
    "Thai policy retry fell back to extractive or no_data",
)
rag_rate_limited_total = Counter(
    "spark_rag_rate_limited_total",
    "RAG query rate limit rejections",
    ["scope"],
)
rag_fallback_level_histogram = Histogram(
    "spark_rag_fallback_level",
    "Fallback ladder level used for successful RAG answers",
    buckets=[0, 1, 2, 3, 4, 5],
)
reranker_degraded_total = Counter(
    "spark_reranker_degraded_total",
    "Cross-encoder reranker degraded to fusion fallback",
    ["reason"],
)
reranker_queue_depth = Gauge(
    "spark_reranker_queue_depth",
    "In-flight reranker batch jobs",
)
vector_drift_detected_total = Counter(
    "spark_vector_drift_detected_total",
    "PG ↔ Qdrant generation drift documents detected during reconcile",
    ["factory_id"],
)
ingest_vector_drift_detected_total = Counter(
    "spark_ingest_vector_drift_detected_total",
    "PG ↔ Qdrant vector mirror drift detected during ingest reconcile",
    ["factory_id"],
)
ingest_purge_backlog = Gauge(
    "spark_ingest_purge_backlog",
    "Pending ingest purge outbox rows awaiting Qdrant cleanup",
)
ingest_purge_exhausted_total = Counter(
    "spark_ingest_purge_exhausted_total",
    "Ingest purge outbox rows that exhausted retry budget",
)
ingest_dlq_total = Counter(
    "spark_ingest_dlq_total",
    "Ingest jobs routed to DLQ",
    ["reason_code", "doc_type"],
)
ingest_quarantine_total = Counter(
    "spark_ingest_quarantine_total",
    "Documents quarantined during ingest trust scan",
    ["doc_type"],
)
ingest_quality_slo_breach_total = Counter(
    "spark_ingest_quality_slo_breach_total",
    "Ingest finalize blocked by content quality SLO",
    ["slo_name"],
)
ingest_compute_pool_queue_depth = Gauge(
    "spark_ingest_compute_pool_queue_depth",
    "In-flight ingest dense/sparse encode jobs awaiting thread pool",
)
rag_retrieval_leg_seconds = Histogram(
    "spark_rag_retrieval_leg_seconds",
    "RAG retrieval stage latency",
    ["leg"],
)
rag_rerank_gate_fail_total = Counter(
    "spark_rag_rerank_gate_fail_total",
    "Rerank relevance gate failures",
    ["intent", "degraded"],
)
ingest_quarantine_backlog = Gauge(
    "spark_ingest_quarantine_backlog",
    "Documents currently in quarantined ingest status (approximate from events)",
)
ingest_partial_swap_total = Counter(
    "spark_ingest_partial_swap_total",
    "Explicit partial ingest swaps committed to the live index",
    ["document_type"],
)
deprecated_config_usage_total = Counter(
    "spark_deprecated_config_usage_total",
    "Deprecated environment variables still set at startup",
    ["key"],
)

event_bus_dropped_total = Counter(
    "spark_event_bus_dropped_total",
    "SSE pub/sub local queue drops under backpressure",
    ["channel"],
)

# Semantic cache metrics
semantic_cache_hit_total = Counter(
    "spark_semantic_cache_hit_total",
    "Semantic similarity cache hits",
)
semantic_cache_miss_total = Counter(
    "spark_semantic_cache_miss_total",
    "Semantic similarity cache misses",
)
semantic_cache_similarity = Histogram(
    "spark_semantic_cache_similarity",
    "Best similarity score from semantic cache lookups",
    buckets=(0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.95, 0.98, 1.0),
)


def _normalize_path(path: str) -> str:
    """Collapse UUIDs and trailing IDs so cardinality stays bounded."""
    import re

    parts = []
    for seg in path.split("/"):
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", seg):
            parts.append("{id}")
        elif re.fullmatch(r"\d+", seg):
            parts.append("{num}")
        else:
            parts.append(seg)
    return "/".join(parts)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = _normalize_path(request.url.path)
        http_requests_total.labels(request.method, path, response.status_code).inc()
        http_request_seconds.labels(request.method, path).observe(elapsed)
        return response
