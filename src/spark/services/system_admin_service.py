"""Super Admin telemetry — infrastructure health for God Mode dashboard."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal, engine
from spark.core.llm_profile import embedding_dimension, load_llm_profile
from spark.core.logging import get_logger
from spark.core.qdrant import get_async_qdrant_client
from spark.core.qdrant_strategy import collection_suffix_version, get_strategy
from spark.core.qdrant_strategy import known_collections as _known_qdrant_collections
from spark.db.models.chat import ChatMessage, ChatSession
from spark.db.models.docs import Document
from spark.db.models.org import User
from spark.db.models.ingestion import IngestionError, IngestionJob
from spark.services.observability_service import ObservabilityService, _parse_scalar
from spark.retrieval.token_counter import get_token_counter
from spark.retrieval.circuit.dependency_breaker import (
    clear_maintenance_mode,
    get_rag_circuit_status,
    read_admin_flag,
    reset_rag_circuit_manual,
    set_maintenance_mode,
)
from spark.storage import check_storage_health

log = get_logger(__name__)

# Rough USD estimates for dashboard cost projection (override via env in future).
_LLM_COST_PER_1K_PROMPT = 0.00015
_LLM_COST_PER_1K_COMPLETION = 0.0006
_EMBED_COST_PER_1K = 0.00002


class SystemAdminService:
    def __init__(self) -> None:
        self._prometheus = ObservabilityService()

    @staticmethod
    async def _isolated_db(fn, /, *args, **kwargs):
        """Run a DB-bound coroutine on its own session (safe for asyncio.gather)."""
        async with AsyncSessionLocal() as session:
            return await fn(session, *args, **kwargs)

    async def fetch_dashboard(self, session: AsyncSession) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=15)
        since_24h = now - timedelta(hours=24)

        traffic_task = self._fetch_traffic()
        llm_task = self._isolated_db(self._fetch_llm_usage, since_24h)
        qdrant_task = self._isolated_db(self._fetch_qdrant_stats)
        postgres_task = self._isolated_db(self._fetch_postgres_stats)
        storage_task = self._isolated_db(self._fetch_storage_stats)
        workers_task = self._isolated_db(self._fetch_worker_stats)
        agentic_task = asyncio.to_thread(self._fetch_agentic_circuit)
        rag_task = self._fetch_rag_circuit()
        shadow_task = asyncio.to_thread(self._fetch_shadow_routing_stats)
        gateway_task = self._fetch_llm_gateway_health()
        maintenance_task = self._fetch_maintenance()
        otel_task = self._fetch_otel_tracing()
        eval_task = self._fetch_eval_metrics()
        embed_shadow_task = self._fetch_embed_shadow()
        semantic_cache_task = self._isolated_db(self._fetch_semantic_cache)
        health_task = self._fetch_health_summary()
        users_task = self._isolated_db(self._fetch_users_stats)
        timeseries_task = self._isolated_db(self._fetch_timeseries)

        results = await asyncio.gather(
            traffic_task,
            llm_task,
            qdrant_task,
            postgres_task,
            storage_task,
            workers_task,
            agentic_task,
            rag_task,
            shadow_task,
            gateway_task,
            maintenance_task,
            otel_task,
            eval_task,
            embed_shadow_task,
            semantic_cache_task,
            health_task,
            users_task,
            timeseries_task,
            return_exceptions=True,
        )

        def _unwrap(idx: int, default: dict[str, Any]) -> dict[str, Any]:
            val = results[idx]
            if isinstance(val, Exception):
                log.warning("system_admin_section_failed", section=idx, error=str(val)[:200])
                return {**default, "error": str(val)[:200]}
            return val  # type: ignore[return-value]

        payload: dict[str, Any] = {
            "generated_at": now.isoformat(),
            "traffic": _unwrap(0, {}),
            "llm_usage": _unwrap(1, {}),
            "qdrant": _unwrap(2, {}),
            "postgres": _unwrap(3, {}),
            "storage": _unwrap(4, {}),
            "workers": _unwrap(5, {}),
            "agentic_circuit": _unwrap(6, {}),
            "rag_circuit": _unwrap(7, {}),
            "shadow_routing": _unwrap(8, {}),
            "llm_gateway": _unwrap(9, {}),
            "maintenance": _unwrap(10, {"enabled": False}),
            "otel_tracing": _unwrap(11, {"enabled": False}),
            "eval_quality": _unwrap(12, {"has_report": False}),
            "embed_shadow": _unwrap(13, {"enabled": False}),
            "semantic_cache": _unwrap(14, {"enabled": False}),
            "health_summary": _unwrap(15, {"status": "unknown", "overall_ok": False}),
            "users": _unwrap(16, {}),
            "timeseries": _unwrap(17, {"days": 7}),
            "active_users_window_minutes": 15,
            "active_users_since": window_start.isoformat(),
        }
        payload["incidents"] = self._build_incidents(payload)
        return payload

    @staticmethod
    def _build_incidents(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Derive NOC incident feed from the dashboard snapshot."""
        at = str(snapshot.get("generated_at") or "")
        incidents: list[dict[str, Any]] = []

        def add(severity: str, title: str, detail: str, source: str) -> None:
            incidents.append(
                {
                    "severity": severity,
                    "title": title,
                    "detail": detail[:200],
                    "source": source,
                    "at": at,
                }
            )

        health = snapshot.get("health_summary") or {}
        for conn in health.get("connectivity") or []:
            if not isinstance(conn, dict):
                continue
            if conn.get("ok"):
                continue
            sev = "warn" if conn.get("degraded") else "critical"
            name = str(conn.get("name") or "service")
            err = str(conn.get("error") or "check failed")
            add(sev, f"{name} unavailable", err, "connectivity")

        maintenance = snapshot.get("maintenance") or {}
        if maintenance.get("enabled"):
            msg = str(maintenance.get("message") or "read-only for users")
            add("warn", "Maintenance mode ON", msg, "maintenance")

        agentic = snapshot.get("agentic_circuit") or {}
        if agentic.get("open"):
            add(
                "critical",
                "Agentic circuit OPEN",
                f"routing={agentic.get('routing_mode', 'unknown')}",
                "agentic",
            )

        rag = snapshot.get("rag_circuit") or {}
        if rag.get("open"):
            add("critical", "RAG circuit OPEN", "retrieval may be blocked", "rag")

        workers = snapshot.get("workers") or {}
        failed = int(workers.get("failed_ingest_jobs") or 0)
        if failed > 0:
            add("warn", f"Failed ingest jobs (7d): {failed}", "inspect ingest logs / admin ingest", "workers")

        backlog = int(workers.get("ingest_queue_backlog") or 0)
        if backlog > 20:
            add("warn", f"Ingest queue backlog: {backlog}", "consider scaling workers", "workers")

        celery = workers.get("celery") or {}
        if isinstance(celery, dict) and not celery.get("ok"):
            add("critical", "Celery workers down", "ingest/async tasks affected", "workers")

        qdrant = snapshot.get("qdrant") or {}
        if qdrant.get("chunk_drift_alert"):
            add(
                "warn",
                f"Chunk drift: {qdrant.get('chunk_drift', '?')}",
                "run Qdrant sync from Actions",
                "qdrant",
            )

        storage = snapshot.get("storage") or {}
        sh = storage.get("health") if isinstance(storage.get("health"), dict) else {}
        if sh and sh.get("ok") is False:
            add(
                "critical",
                "Storage FAIL",
                str(sh.get("error") or storage.get("error") or "check storage backend")[:200],
                "storage",
            )

        traffic = snapshot.get("traffic") or {}
        err_rate = traffic.get("error_rate_5xx")
        if err_rate is not None:
            try:
                if float(err_rate) > 0.005:
                    add(
                        "warn",
                        f"HTTP 5xx rate {float(err_rate) * 100:.2f}%",
                        "check API logs / upstream",
                        "traffic",
                    )
            except (TypeError, ValueError):
                pass

        if not traffic.get("prometheus_available"):
            add("info", "Prometheus unavailable", "traffic/latency use DB fallback", "metrics")

        gateway = snapshot.get("llm_gateway") or {}
        if gateway.get("healthy") is False:
            add("warn", "LLM gateway unhealthy", str(gateway.get("error") or "check Ollama/embed")[:200], "llm")
        forge_check = (gateway.get("checks") or {}).get("forge")
        if isinstance(forge_check, dict) and forge_check.get("ok") is False:
            add(
                "info",
                "ForgeNode unreachable",
                "optional rerank/embed gateway down — active path uses GPU sidecar + local models",
                "llm",
            )

        eval_q = snapshot.get("eval_quality") or {}
        if eval_q.get("has_report") and eval_q.get("gate_passed") is False:
            add("warn", "Eval quality gate FAILED", "see reports/ci_eval_report.json", "eval")

        postgres = snapshot.get("postgres") or {}
        slow = postgres.get("slow_queries") or []
        if isinstance(slow, list) and slow:
            top = slow[0] if isinstance(slow[0], dict) else {}
            dur = top.get("duration_sec", "?")
            add("info", f"Slow queries active: {len(slow)}", f"longest ~{dur}s", "postgres")

        if not incidents:
            ok_n = sum(1 for c in (health.get("connectivity") or []) if isinstance(c, dict) and c.get("ok"))
            add("info", "All systems operational", f"{ok_n} connectivity checks OK", "system")

        order = {"critical": 0, "warn": 1, "info": 2}
        incidents.sort(key=lambda x: order.get(str(x.get("severity")), 9))
        return incidents[:12]

    async def _fetch_traffic(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "requests_per_sec": None,
            "p95_latency_sec": None,
            "prometheus_available": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._prometheus.timeout) as client:
                for key, expr in (
                    ("requests_per_sec", "sum(rate(spark_http_requests_total[1m]))"),
                    (
                        "p95_latency_sec",
                        "histogram_quantile(0.95, sum by (le) (rate(spark_http_request_seconds_bucket[5m])))",
                    ),
                    ("sse_connections", "sum(spark_sse_connections_active)"),
                    (
                        "error_rate_5xx",
                        (
                            "sum(rate(spark_http_requests_total{status=~\"5..\"}[5m])) "
                            "/ clamp_min(sum(rate(spark_http_requests_total[5m])), 0.001)"
                        ),
                    ),
                ):
                    result = await self._prometheus._query(client, expr)
                    out[key] = _parse_scalar(result)
            out["prometheus_available"] = True
        except Exception as exc:
            out["error"] = str(exc)[:200]

        try:
            async with AsyncSessionLocal() as session:
                active = await session.scalar(
                    select(func.count(func.distinct(ChatSession.user_id))).where(
                        ChatSession.updated_at >= datetime.now(timezone.utc) - timedelta(minutes=15),
                        ChatSession.user_id.is_not(None),
                    )
                )
                out["active_users"] = int(active or 0)
                out["active_sessions_15m"] = int(
                    (
                        await session.scalar(
                            select(func.count()).select_from(ChatSession).where(
                                ChatSession.updated_at
                                >= datetime.now(timezone.utc) - timedelta(minutes=15)
                            )
                        )
                    )
                    or 0
                )
                out["messages_24h"] = int(
                    (
                        await session.scalar(
                            select(func.count()).select_from(ChatMessage).where(
                                ChatMessage.created_at
                                >= datetime.now(timezone.utc) - timedelta(hours=24)
                            )
                        )
                    )
                    or 0
                )
        except Exception:
            out["active_users"] = 0
            out["active_sessions_15m"] = 0
            out["messages_24h"] = 0

        return out

    async def _fetch_llm_usage(self, session: AsyncSession, since: datetime) -> dict[str, Any]:
        counter = get_token_counter()
        rows = (
            await session.execute(
                select(
                    ChatMessage.role,
                    ChatMessage.content,
                    ChatMessage.retrieval_snapshot,
                    ChatMessage.sources,
                    ChatMessage.confidence_tier,
                    ChatMessage.cache_hit,
                ).where(ChatMessage.created_at >= since)
            )
        ).all()

        prompt_tokens = 0
        completion_tokens = 0
        actual_prompt_tokens = 0
        actual_completion_tokens = 0
        actual_total_tokens = 0
        actual_request_count = 0
        actual_models: set[str] = set()
        actual_providers: set[str] = set()
        answer_count = 0
        cited_answer_count = 0
        no_data_count = 0
        high_confidence_count = 0
        cache_hit_count = 0
        for role, content, snapshot, sources, confidence_tier, cache_hit in rows:
            usage = (snapshot or {}).get("llm_usage") if isinstance(snapshot, dict) else None
            if isinstance(usage, dict):
                actual_prompt_tokens += int(usage.get("prompt_tokens") or 0)
                actual_completion_tokens += int(usage.get("completion_tokens") or 0)
                actual_total_tokens += int(usage.get("total_tokens") or 0)
                actual_request_count += 1
                for model in usage.get("models") or []:
                    actual_models.add(str(model))
                for provider in usage.get("providers") or []:
                    actual_providers.add(str(provider))
            tokens = counter.count(content or "", settings.ollama_llm_model)
            if role in ("user", "human"):
                prompt_tokens += tokens
            elif role == "assistant":
                completion_tokens += tokens
                answer_count += 1
                if isinstance(sources, list) and len(sources) > 0:
                    cited_answer_count += 1
                answer_path = (
                    str((snapshot or {}).get("answer_path") or "")
                    if isinstance(snapshot, dict)
                    else ""
                )
                normalized_content = (content or "").strip()
                if answer_path == "no_data" or normalized_content.startswith(
                    ("ไม่พบข้อมูล", "ยังไม่พบข้อมูล", "ไม่พบเครื่องจักร", "เครื่องที่เลือกไม่ตรง")
                ):
                    no_data_count += 1
                if confidence_tier == "high":
                    high_confidence_count += 1
                if cache_hit:
                    cache_hit_count += 1

        embed_rows = (
            await session.execute(
                select(func.coalesce(func.sum(Document.chunks_count), 0)).where(
                    Document.updated_at >= since
                )
            )
        ).scalar_one()
        embedding_tokens_est = int(embed_rows or 0) * 180

        display_prompt_tokens = actual_prompt_tokens or prompt_tokens
        display_completion_tokens = actual_completion_tokens or completion_tokens
        prompt_cost = (display_prompt_tokens / 1000) * _LLM_COST_PER_1K_PROMPT
        completion_cost = (display_completion_tokens / 1000) * _LLM_COST_PER_1K_COMPLETION
        embed_cost = (embedding_tokens_est / 1000) * _EMBED_COST_PER_1K

        try:
            usd_thb = float(os.getenv("USD_THB_RATE", "33.0"))
        except ValueError:
            usd_thb = 33.0
        total_cost_usd = prompt_cost + completion_cost + embed_cost

        return {
            "window_hours": 24,
            "prompt_tokens": actual_prompt_tokens,
            "completion_tokens": actual_completion_tokens,
            "total_tokens": actual_total_tokens or actual_prompt_tokens + actual_completion_tokens,
            "usage_request_count": actual_request_count,
            "usage_source": "provider" if actual_request_count else "estimated",
            "models": sorted(actual_models),
            "providers": sorted(actual_providers),
            "prompt_tokens_est": display_prompt_tokens,
            "completion_tokens_est": display_completion_tokens,
            "embedding_tokens_est": embedding_tokens_est,
            "estimated_cost_usd": round(total_cost_usd, 4),
            "estimated_cost_thb": round(total_cost_usd * usd_thb, 4),
            "usd_thb_rate": usd_thb,
            "cost_breakdown_usd": {
                "prompt": round(prompt_cost, 4),
                "completion": round(completion_cost, 4),
                "embedding": round(embed_cost, 4),
            },
            "cost_breakdown_thb": {
                "prompt": round(prompt_cost * usd_thb, 4),
                "completion": round(completion_cost * usd_thb, 4),
                "embedding": round(embed_cost * usd_thb, 4),
            },
            "message_count": len(rows),
            "answer_count": answer_count,
            "cited_answer_rate_pct": round(cited_answer_count * 100 / answer_count, 1)
            if answer_count
            else None,
            "no_data_rate_pct": round(no_data_count * 100 / answer_count, 1)
            if answer_count
            else None,
            "high_confidence_rate_pct": round(high_confidence_count * 100 / answer_count, 1)
            if answer_count
            else None,
            "cache_hit_rate_pct": round(cache_hit_count * 100 / answer_count, 1)
            if answer_count
            else None,
        }

    async def _fetch_qdrant_stats(self, session: AsyncSession) -> dict[str, Any]:
        pg_chunks = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(Document.chunks_count), 0))
                )
            ).scalar_one()
            or 0
        )

        client = get_async_qdrant_client()
        collections: list[dict[str, Any]] = []
        total_vectors = 0

        try:
            listed = await client.get_collections()
            names = [c.name for c in listed.collections]
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc)[:200],
                "postgres_chunks_total": pg_chunks,
                "shard_strategy": get_strategy(),
            }

        known_bases = _known_qdrant_collections()
        for name in sorted(names):
            if not any(name == base or name.startswith(f"{base}__") for base in known_bases):
                continue
            try:
                info = await client.get_collection(name)
                points = int(getattr(info, "points_count", 0) or 0)
                total_vectors += points
                status = str(getattr(info, "status", "unknown"))
                cfg = info.config
                vector_size = None
                on_disk = None
                # Collections use a *named* dense vector ("dense") for hybrid
                # dense+sparse search, so params.vectors is {"dense": {...}},
                # not a single unnamed VectorParams — .size/.on_disk directly
                # on it raised AttributeError and silently dropped this field.
                if cfg and cfg.params and cfg.params.vectors:
                    vectors_cfg = cfg.params.vectors
                    dense_cfg = (
                        vectors_cfg.get("dense") or next(iter(vectors_cfg.values()), None)
                        if isinstance(vectors_cfg, dict)
                        else vectors_cfg
                    )
                    if isinstance(dense_cfg, dict):
                        vector_size = dense_cfg.get("size")
                        on_disk = dense_cfg.get("on_disk")
                    elif dense_cfg is not None:
                        vector_size = getattr(dense_cfg, "size", None)
                        on_disk = getattr(dense_cfg, "on_disk", None)
                collections.append(
                    {
                        "name": name,
                        "points_count": points,
                        "status": status,
                        "vector_size": vector_size,
                        "on_disk": on_disk,
                        "indexed_fields_count": len(getattr(info, "payload_schema", {}) or {}),
                    }
                )
            except Exception as exc:
                collections.append({"name": name, "error": str(exc)[:120]})

        drift = pg_chunks - total_vectors
        from spark.services.vector_reconcile_service import get_last_reconcile_summary

        last_reconcile = get_last_reconcile_summary()
        return {
            "available": True,
            "host": f"{settings.qdrant_host}:{settings.qdrant_port}",
            "shard_strategy": get_strategy(),
            "collection_suffix_version": collection_suffix_version(),
            "collections": collections,
            "postgres_chunks_total": pg_chunks,
            "qdrant_points_total": total_vectors,
            "chunk_drift": drift,
            "chunk_drift_alert": abs(drift) > max(50, int(pg_chunks * 0.02)),
            "expected_embedding_dim": embedding_dimension(),
            "last_reconcile": last_reconcile,
        }

    async def _fetch_postgres_stats(self, session: AsyncSession) -> dict[str, Any]:
        pool = engine.sync_engine.pool
        pool_status = pool.status() if hasattr(pool, "status") else ""

        def _pool_int(name: str) -> int | None:
            fn = getattr(pool, name, None)
            if not callable(fn):
                return None
            try:
                return int(fn())
            except Exception:
                return None

        base_size = _pool_int("size")
        checked_out = _pool_int("checkedout")
        checked_in = _pool_int("checkedin")
        # QueuePool.overflow() starts at -pool_size; only positive values mean
        # overflow connections are actually in use.
        overflow_raw = _pool_int("overflow")
        overflow_in_use = max(0, overflow_raw) if overflow_raw is not None else None

        locks = (
            await session.execute(
                text(
                    "SELECT mode, COUNT(*) AS cnt FROM pg_locks "
                    "WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                    "GROUP BY mode ORDER BY cnt DESC LIMIT 8"
                )
            )
        ).mappings().all()

        slow = (
            await session.execute(
                text(
                    "SELECT pid, usename, state, "
                    "EXTRACT(EPOCH FROM (now() - query_start))::int AS duration_sec, "
                    "LEFT(query, 120) AS query_preview "
                    "FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND state = 'active' "
                    "AND query NOT ILIKE '%pg_stat_activity%' "
                    "AND query_start < now() - interval '2 seconds' "
                    "ORDER BY query_start ASC LIMIT 5"
                )
            )
        ).mappings().all()

        return {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_status": pool_status,
            "pool_capacity": (base_size if base_size is not None else settings.db_pool_size)
            + max(settings.db_max_overflow, 0),
            "pool_checked_out": checked_out,
            "pool_checked_in": checked_in,
            "pool_overflow_in_use": overflow_in_use,
            "locks": [dict(row) for row in locks],
            "slow_queries": [dict(row) for row in slow],
        }

    async def _fetch_storage_stats(self, session: AsyncSession) -> dict[str, Any]:
        gib = 1024**3
        doc_bytes = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(Document.file_size_bytes), 0))
                )
            ).scalar_one()
            or 0
        )
        doc_count = int(
            (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        )
        health = await asyncio.to_thread(check_storage_health)
        backend = (settings.storage_backend or "local").lower()

        postgres_bytes = int(
            (await session.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
            or 0
        )

        # Qdrant has no direct disk-usage API — estimate from point count and
        # vector dimension (dense float32 + ~30% overhead for HNSW graph,
        # sparse vector, and payload). Labeled as an estimate, not measured.
        qdrant_bytes_estimate: int | None = None
        try:
            client = get_async_qdrant_client()
            listed = await client.get_collections()
            known_bases = _known_qdrant_collections()
            total_points = 0
            for c in listed.collections:
                if not any(c.name == base or c.name.startswith(f"{base}__") for base in known_bases):
                    continue
                info = await client.get_collection(c.name)
                total_points += int(getattr(info, "points_count", 0) or 0)
            dim = embedding_dimension()
            qdrant_bytes_estimate = int(total_points * dim * 4 * 1.3)
        except Exception:
            pass

        return {
            "backend": backend,
            "document_count": doc_count,
            "document_bytes_total": doc_bytes,
            "document_gib": round(doc_bytes / gib, 3),
            "postgres_bytes_total": postgres_bytes,
            "postgres_gib": round(postgres_bytes / gib, 3),
            "qdrant_bytes_estimate": qdrant_bytes_estimate,
            "qdrant_gib_estimate": round(qdrant_bytes_estimate / gib, 3) if qdrant_bytes_estimate else None,
            "health": health,
        }

    async def _fetch_worker_stats(self, session: AsyncSession) -> dict[str, Any]:
        from spark.workers.celery_app import check_celery_worker_health

        celery_health = await asyncio.to_thread(check_celery_worker_health)

        queued = int(
            (
                await session.execute(
                    select(func.count()).select_from(IngestionJob).where(
                        IngestionJob.status.in_(("queued", "running"))
                    )
                )
            ).scalar_one()
        )
        # Only recent failures are actionable — terminal rows from crashes and
        # config errors that were since fixed otherwise raise a permanent
        # incident (the docs behind the old rows are all re-ingested fine).
        failed_since = datetime.now(timezone.utc) - timedelta(days=7)
        failed_jobs = int(
            (
                await session.execute(
                    select(func.count()).select_from(IngestionJob).where(
                        IngestionJob.status == "failed",
                        IngestionJob.created_at >= failed_since,
                    )
                )
            ).scalar_one()
        )
        dead_letter_errors = int(
            (
                await session.execute(
                    select(func.count()).select_from(IngestionError).where(
                        IngestionError.created_at >= failed_since
                    )
                )
            ).scalar_one()
        )

        queue_depth = 0
        try:
            import redis

            client = redis.from_url(settings.redis_url, socket_connect_timeout=2.0)
            try:
                queue_depth = int(client.llen("celery"))
            finally:
                client.close()
        except Exception:
            pass

        return {
            "celery": celery_health,
            "ingest_queue_backlog": queued,
            "celery_broker_queue_depth": queue_depth,
            "failed_ingest_jobs": failed_jobs,
            "ingestion_error_rows": dead_letter_errors,
        }

    def _fetch_agentic_circuit(self) -> dict[str, Any]:
        # The agentic routing path is not built into this deployment — there is
        # no live circuit breaker to report. `enabled: False` lets the dashboard
        # show "disabled" honestly instead of a fake healthy breaker.
        return {
            "enabled": False,
            "open": False,
            "routing_mode": "legacy",
            "canary_pct": 0,
            "flag": None,
            "note": "agentic routing not enabled in this build",
        }

    async def _fetch_maintenance(self) -> dict[str, Any]:
        flag = read_admin_flag()
        return {
            "enabled": flag is not None,
            "message": str((flag or {}).get("reason") or ""),
            "detail": flag or {},
        }

    async def _fetch_rag_circuit(self) -> dict[str, Any]:
        status = await get_rag_circuit_status()
        return {
            "open": bool(status.get("open")),
            "flag": status.get("admin_flag"),
            "window_sec": int(settings.rag_circuit_window_sec or 600),
            **{k: v for k, v in status.items() if k not in ("open", "admin_flag")},
        }

    async def fetch_rag_circuit_status(self) -> dict[str, Any]:
        from spark.retrieval.safety.circuit_breaker import get_rag_circuit_status

        return await get_rag_circuit_status()

    async def reset_rag_circuit(self, *, operator: str) -> dict[str, Any]:
        from spark.retrieval.safety.circuit_breaker import (
            is_rag_circuit_open_async,
            reset_rag_circuit_manual,
        )

        had_open = await reset_rag_circuit_manual(operator=operator, reason="super_admin_dashboard")
        return {"had_open_circuit": had_open, "open": await is_rag_circuit_open_async()}

    def _fetch_shadow_routing_stats(self) -> dict[str, Any]:
        return {"enabled": False, "active": False, "routing_mode": "legacy"}

    async def _fetch_llm_gateway_health(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}

        profile_name = settings.llm_profile
        model_name = settings.ollama_llm_model
        embed_model = settings.ollama_embed_model
        profile: dict[str, Any] = {}
        try:
            profile = load_llm_profile()
            model_name = str(profile.get("llm_model") or model_name)
            embed_model = str(profile.get("embed_model") or embed_model)
        except Exception:
            pass

        # Profile-aware reachability check — mirrors readyz_probe.py. openai/vllm
        # profiles (e.g. gemma_remote -> api.kcalsion.com) are a WAF-protected,
        # authenticated gateway, not a native Ollama server: hitting
        # ollama_base_url/api/tags there always fails (wrong host, wrong path,
        # no auth), which is why this used to report "unhealthy" unconditionally
        # for any remote-gateway profile.
        provider = str(profile.get("provider", "ollama")).lower()
        try:
            from spark.core.llm_client import openai_gateway_headers

            if provider in ("openai", "vllm"):
                base = str(profile.get("base_url") or settings.ollama_base_url).rstrip("/")
                if not base.endswith("/v1"):
                    base = f"{base}/v1"
                headers = dict(openai_gateway_headers())
                api_key = profile.get("api_key") or settings.ollama_api_key
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(f"{base}/models", headers=headers)
                checks["llm"] = {"ok": r.status_code < 500, "provider": provider, "status": r.status_code}
            else:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    r = await client.get(f"{settings.ollama_base_url}/api/tags")
                checks["llm"] = {"ok": r.status_code < 500, "provider": "ollama", "status": r.status_code}
        except Exception as exc:
            checks["llm"] = {"ok": False, "provider": provider, "error": str(exc)[:120]}

        expected_dim = embedding_dimension()
        dim_ok = True
        try:
            client = get_async_qdrant_client()
            info = await client.get_collection(settings.qdrant_collection)
            vectors = info.config.params.vectors  # type: ignore[union-attr]
            if isinstance(vectors, dict):
                first = next(iter(vectors.values()), None)
                existing = getattr(first, "size", None) if first is not None else None
            else:
                existing = getattr(vectors, "size", None)
            dim_ok = existing is not None and existing == expected_dim
            checks["embedding_dim"] = {
                "ok": dim_ok,
                "qdrant_dim": existing,
                "profile_dim": expected_dim,
            }
        except Exception as exc:
            checks["embedding_dim"] = {"ok": False, "error": str(exc)[:120]}

        try:
            from spark.core.forge_client import fetch_forge_status, forge_enabled

            if forge_enabled():
                forge_status = await fetch_forge_status()
                checks["forge"] = {
                    "ok": bool(forge_status.get("ok")),
                    "base_url": forge_status.get("base_url"),
                    "health": forge_status.get("health"),
                    "embed": forge_status.get("embed"),
                    "rerank": forge_status.get("rerank"),
                    "models": forge_status.get("models"),
                }
        except Exception as exc:
            checks["forge"] = {"ok": False, "error": str(exc)[:120]}

        return {
            "llm_profile": profile_name,
            "llm_model": model_name,
            "embed_model": embed_model,
            "checks": checks,
            # ForgeNode is an optional secondary gateway — the active answer path
            # uses the GPU sidecar + local models when it is down, so it must not
            # flip the whole gateway to "unhealthy" (it gets its own incident).
            "healthy": all(
                v.get("ok", False) for k, v in checks.items() if isinstance(v, dict) and k != "forge"
            ),
        }

    async def clear_system_cache(self) -> dict[str, Any]:
        from spark.core.cache import Cache

        deleted = await Cache.get().clear_spark_keys()
        return {"cleared_keys": deleted}

    async def force_qdrant_sync(self, session: AsyncSession) -> dict[str, Any]:
        from spark.core.qdrant import ensure_collection

        ensure_collection()
        stats = await self._fetch_qdrant_stats(session)
        return {
            "action": "ensure_collections_and_reindex_payload",
            "collections_checked": len(stats.get("collections") or []),
            "chunk_drift": stats.get("chunk_drift"),
            "chunk_drift_alert": stats.get("chunk_drift_alert"),
            "details": stats,
        }

    def reset_agentic_circuit(self, *, operator: str) -> dict[str, Any]:
        del operator
        return {"had_open_circuit": False, "open": False, "note": "agentic path disabled"}


    async def _fetch_otel_tracing(self) -> dict[str, Any]:
        import os
        endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
        enabled = bool(endpoint)
        jaeger_ui = ""
        if enabled:
            host = endpoint.split("://")[-1].split(":")[0]
            jaeger_ui = f"http://{host}:16686"
        spans_total: float | None = None
        if enabled:
            try:
                async with httpx.AsyncClient(timeout=self._prometheus.timeout) as client:
                    result = await self._prometheus._query(
                        client,
                        'sum(increase(otel_span_processor_spans_total[1h]))',
                    )
                    spans_total = _parse_scalar(result)
            except Exception:
                pass
        return {
            "enabled": enabled,
            "endpoint": endpoint or "not configured",
            "jaeger_ui": jaeger_ui,
            "service_name": os.getenv("OTEL_SERVICE_NAME", "spark-api"),
            "spans_1h": spans_total,
            "instrumented_components": [
                "chat.ask", "rag.query", "rag.retrieve.vector",
                "rag.retrieve.lexical", "rag.retrieve.fusion",
                "rag.retrieve.rerank", "rag.generate",
                "rag.generate.grounded_llm", "rag.generate.nli_gate",
                "ingest.pipeline",
            ],
        }

    async def _fetch_eval_metrics(self) -> dict[str, Any]:
        from pathlib import Path
        import json

        report_path = Path("reports/ci_eval_report.json")
        last_report: dict[str, Any] | None = None
        if report_path.is_file():
            try:
                last_report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        thresholds: dict[str, Any] = {}
        threshold_path = Path("configs/eval/thresholds.yaml")
        if threshold_path.is_file():
            try:
                import yaml
                thresholds = yaml.safe_load(threshold_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        return {
            "last_report": last_report,
            "thresholds": thresholds,
            "has_report": last_report is not None,
            "gate_passed": last_report.get("gate_passed") if last_report else None,
            "suites_available": [
                "baseline_ci", "baseline", "heldout",
                "safety_critical", "adversarial", "grounding",
            ],
        }

    async def _fetch_embed_shadow(self) -> dict[str, Any]:
        import os
        enabled = os.getenv("EMBED_SHADOW_ENABLED", "").lower() in ("1", "true")
        shadow_model = os.getenv("EMBED_SHADOW_MODEL", "")
        sample_rate = float(os.getenv("EMBED_SHADOW_SAMPLE_RATE", "0.10"))

        overlap_avg: float | None = None
        rbo_avg: float | None = None
        comparisons_1h: float | None = None

        if enabled:
            try:
                async with httpx.AsyncClient(timeout=self._prometheus.timeout) as client:
                    for key, expr in (
                        ("overlap_avg", "avg(spark_embed_shadow_overlap_at_k)"),
                        ("rbo_avg", "avg(spark_embed_shadow_rbo)"),
                        ("comparisons_1h", "sum(increase(spark_embed_shadow_overlap_at_k_count[1h]))"),
                    ):
                        result = await self._prometheus._query(client, expr)
                        val = _parse_scalar(result)
                        if key == "overlap_avg":
                            overlap_avg = val
                        elif key == "rbo_avg":
                            rbo_avg = val
                        else:
                            comparisons_1h = val
            except Exception:
                pass

        from spark.ingestion.embed_profile import EmbedProfile
        current = EmbedProfile.from_runtime()

        return {
            "enabled": enabled,
            "production_model": current.model_id,
            "shadow_model": shadow_model or "not configured",
            "sample_rate": sample_rate,
            "overlap_avg": overlap_avg,
            "rbo_avg": rbo_avg,
            "comparisons_1h": comparisons_1h,
        }

    async def _fetch_semantic_cache(self, session: AsyncSession) -> dict[str, Any]:
        import os
        enabled = settings.semantic_cache_enabled or os.getenv("SEMANTIC_CACHE_ENABLED", "").lower() in ("1", "true")
        threshold = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", str(settings.semantic_cache_threshold)))

        from spark.db.models.qa_cache import VerifiedQACache

        total_entries = (
            await session.execute(select(func.count(VerifiedQACache.cache_id)))
        ).scalar() or 0

        entries_with_embedding = (
            await session.execute(
                select(func.count(VerifiedQACache.cache_id)).where(
                    VerifiedQACache.question_embedding.isnot(None)
                )
            )
        ).scalar() or 0

        hits_total: float | None = None
        miss_total: float | None = None
        avg_similarity: float | None = None
        try:
            async with httpx.AsyncClient(timeout=self._prometheus.timeout) as client:
                for key, expr in (
                    ("hits", "sum(spark_semantic_cache_hit_total)"),
                    ("misses", "sum(spark_semantic_cache_miss_total)"),
                    ("similarity", "avg(spark_semantic_cache_similarity)"),
                ):
                    result = await self._prometheus._query(client, expr)
                    val = _parse_scalar(result)
                    if key == "hits":
                        hits_total = val
                    elif key == "misses":
                        miss_total = val
                    else:
                        avg_similarity = val
        except Exception:
            pass

        hit_rate: float | None = None
        if hits_total is not None and miss_total is not None:
            total_lookups = (hits_total or 0) + (miss_total or 0)
            if total_lookups > 0:
                hit_rate = round((hits_total or 0) / total_lookups * 100, 2)

        return {
            "enabled": enabled,
            "threshold": threshold,
            "total_cache_entries": total_entries,
            "entries_with_embedding": entries_with_embedding,
            "embedding_coverage_pct": round(entries_with_embedding / max(total_entries, 1) * 100, 1),
            "hits_total": hits_total,
            "misses_total": miss_total,
            "hit_rate_pct": hit_rate,
            "avg_similarity": avg_similarity,
        }

    async def _fetch_health_summary(self) -> dict[str, Any]:
        from spark.core.readyz_probe import readyz_full

        try:
            body, status_code = await readyz_full(bypass_cache=True)
        except Exception as exc:
            return {
                "status": "error",
                "overall_ok": False,
                "http_status": 503,
                "checks": {},
                "connectivity": [],
                "error": str(exc)[:200],
            }

        checks: dict[str, Any] = body.get("checks") or {}
        connectivity: list[dict[str, Any]] = []
        for name in ("postgres", "redis", "qdrant", "llm", "storage", "celery"):
            check = checks.get(name) or {}
            connectivity.append(
                {
                    "name": name,
                    "ok": bool(check.get("ok")),
                    "degraded": bool(check.get("degraded")),
                    "error": check.get("error"),
                }
            )

        failed = sum(1 for c in connectivity if not c["ok"] and not c.get("degraded"))
        degraded = sum(1 for c in connectivity if not c["ok"] and c.get("degraded"))

        return {
            "status": body.get("status", "unknown"),
            "overall_ok": body.get("status") == "ready",
            "http_status": status_code,
            "checks": checks,
            "connectivity": connectivity,
            "failed_count": failed,
            "degraded_count": degraded,
        }

    async def _fetch_users_stats(self, session: AsyncSession) -> dict[str, Any]:
        now = datetime.now(timezone.utc)

        total = int((await session.execute(select(func.count()).select_from(User))).scalar_one())
        super_admins = int(
            (
                await session.execute(
                    select(func.count()).select_from(User).where(User.is_super_admin.is_(True))
                )
            ).scalar_one()
        )
        active_accounts = int(
            (
                await session.execute(
                    select(func.count()).select_from(User).where(User.is_active.is_(True))
                )
            ).scalar_one()
        )

        async def _distinct_users(minutes: int) -> int:
            since = now - timedelta(minutes=minutes)
            return int(
                (
                    await session.scalar(
                        select(func.count(func.distinct(ChatSession.user_id))).where(
                            ChatSession.updated_at >= since,
                            ChatSession.user_id.is_not(None),
                        )
                    )
                )
                or 0
            )

        async def _session_count(minutes: int) -> int:
            since = now - timedelta(minutes=minutes)
            return int(
                (
                    await session.scalar(
                        select(func.count()).select_from(ChatSession).where(
                            ChatSession.updated_at >= since
                        )
                    )
                )
                or 0
            )

        return {
            "total_registered": total,
            "active_accounts": active_accounts,
            "super_admins": super_admins,
            "active_users_15m": await _distinct_users(15),
            "active_users_1h": await _distinct_users(60),
            "active_users_24h": await _distinct_users(24 * 60),
            "active_sessions_15m": await _session_count(15),
            "active_sessions_1h": await _session_count(60),
        }

    @staticmethod
    def _fill_daily_series(
        rows: list[dict[str, Any]], *, days: int = 7
    ) -> list[dict[str, Any]]:
        """Ensure consecutive UTC day buckets (zero-filled gaps)."""
        today = datetime.now(timezone.utc).date()
        by_day = {str(r["date"]): int(r["value"]) for r in rows}
        out: list[dict[str, Any]] = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            out.append({"date": key, "value": by_day.get(key, 0)})
        return out

    @staticmethod
    def _fill_hourly_series(
        rows: list[dict[str, Any]], *, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Ensure consecutive UTC hour buckets (zero-filled gaps)."""
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        by_hour: dict[str, int] = {}
        for r in rows:
            hour = r.get("hour")
            if hour is None:
                continue
            key = hour.isoformat() if hasattr(hour, "isoformat") else str(hour)
            by_hour[key[:13]] = int(r.get("value") or 0)

        out: list[dict[str, Any]] = []
        for offset in range(hours - 1, -1, -1):
            hour = now - timedelta(hours=offset)
            key = hour.isoformat()[:13]
            out.append(
                {
                    "ts": int(hour.timestamp()),
                    "label": hour.strftime("%H:%M"),
                    "value": by_hour.get(key, 0),
                }
            )
        return out

    async def _fetch_timeseries(self, session: AsyncSession) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        start_24h = now - timedelta(hours=24)
        days = 7

        dau_rows = (
            await session.execute(
                text(
                    "SELECT (date_trunc('day', updated_at AT TIME ZONE 'UTC'))::date AS day, "
                    "COUNT(DISTINCT user_id) AS cnt "
                    "FROM chat_sessions "
                    "WHERE updated_at >= :start AND user_id IS NOT NULL "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start},
            )
        ).mappings().all()

        session_rows = (
            await session.execute(
                text(
                    "SELECT (date_trunc('day', created_at AT TIME ZONE 'UTC'))::date AS day, "
                    "COUNT(*) AS cnt "
                    "FROM chat_sessions "
                    "WHERE created_at >= :start "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start},
            )
        ).mappings().all()

        # Token counts use the same Thai-aware counter as the 24h KPI stat (get_token_counter),
        # not a flat chars/4 estimate — chars/4 assumes Latin text and badly undercounts Thai
        # (~1.8 chars/token), which made this chart disagree with the "Tokens 24h" KPI above it.
        msg_detail_rows = (
            await session.execute(
                text(
                    "SELECT (date_trunc('day', created_at AT TIME ZONE 'UTC'))::date AS day, "
                    "role, content "
                    "FROM chat_messages "
                    "WHERE created_at >= :start"
                ),
                {"start": start},
            )
        ).all()

        token_counter = get_token_counter()
        msg_agg: dict[str, dict[str, int]] = {}
        for day, role, content in msg_detail_rows:
            bucket = msg_agg.setdefault(
                str(day), {"msg_cnt": 0, "prompt_tokens": 0, "completion_tokens": 0}
            )
            bucket["msg_cnt"] += 1
            tokens = token_counter.count(content or "", settings.ollama_llm_model)
            if role in ("user", "human"):
                bucket["prompt_tokens"] += tokens
            elif role == "assistant":
                bucket["completion_tokens"] += tokens

        msg_rows = [{"day": day, **agg} for day, agg in sorted(msg_agg.items())]

        ingest_rows = (
            await session.execute(
                text(
                    "SELECT (date_trunc('day', created_at AT TIME ZONE 'UTC'))::date AS day, "
                    "COUNT(*) AS cnt "
                    "FROM ingestion_jobs "
                    "WHERE created_at >= :start "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start},
            )
        ).mappings().all()

        ingest_status_rows_by_day = (
            await session.execute(
                text(
                    "SELECT (date_trunc('day', created_at AT TIME ZONE 'UTC'))::date AS day, "
                    "COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
                    "COUNT(*) FILTER (WHERE status IN ('failed', 'dlq')) AS failed, "
                    "COUNT(*) FILTER (WHERE status = 'deleted') AS deleted, "
                    "COUNT(*) FILTER (WHERE status = 'pending_release') AS pending_review, "
                    "COUNT(*) FILTER ("
                    "  WHERE status NOT IN ('completed', 'failed', 'dlq', 'deleted', 'pending_release')"
                    ") AS queued "
                    "FROM ingestion_jobs "
                    "WHERE created_at >= :start "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start},
            )
        ).mappings().all()

        hourly_msg_rows = (
            await session.execute(
                text(
                    "SELECT date_trunc('hour', created_at AT TIME ZONE 'UTC') AS hour, "
                    "COUNT(*) AS cnt "
                    "FROM chat_messages "
                    "WHERE created_at >= :start "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start_24h},
            )
        ).mappings().all()

        hourly_session_rows = (
            await session.execute(
                text(
                    "SELECT date_trunc('hour', updated_at AT TIME ZONE 'UTC') AS hour, "
                    "COUNT(DISTINCT user_id) AS cnt "
                    "FROM chat_sessions "
                    "WHERE updated_at >= :start AND user_id IS NOT NULL "
                    "GROUP BY 1 ORDER BY 1"
                ),
                {"start": start_24h},
            )
        ).mappings().all()

        ingest_status_rows = (
            await session.execute(
                select(IngestionJob.status, func.count())
                .select_from(IngestionJob)
                .group_by(IngestionJob.status)
                .order_by(func.count().desc())
            )
        ).all()

        daily_active_users = self._fill_daily_series(
            [{"date": str(r["day"]), "value": int(r["cnt"] or 0)} for r in dau_rows],
            days=days,
        )
        daily_sessions = self._fill_daily_series(
            [{"date": str(r["day"]), "value": int(r["cnt"] or 0)} for r in session_rows],
            days=days,
        )
        daily_messages = self._fill_daily_series(
            [{"date": str(r["day"]), "value": int(r["msg_cnt"] or 0)} for r in msg_rows],
            days=days,
        )
        daily_tokens_est = self._fill_daily_series(
            [
                {
                    "date": str(r["day"]),
                    "value": int(r["prompt_tokens"] or 0) + int(r["completion_tokens"] or 0),
                }
                for r in msg_rows
            ],
            days=days,
        )
        daily_ingest_jobs = self._fill_daily_series(
            [{"date": str(r["day"]), "value": int(r["cnt"] or 0)} for r in ingest_rows],
            days=days,
        )

        today = datetime.now(timezone.utc).date()
        split_by_day = {str(r["day"]): r for r in msg_rows}
        daily_token_split: list[dict[str, Any]] = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            row = split_by_day.get(key)
            daily_token_split.append(
                {
                    "date": key,
                    "prompt": int(row["prompt_tokens"] or 0) if row else 0,
                    "completion": int(row["completion_tokens"] or 0) if row else 0,
                }
            )

        ingest_status_by_day = {str(r["day"]): r for r in ingest_status_rows_by_day}
        daily_ingest_by_status: list[dict[str, Any]] = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            row = ingest_status_by_day.get(key)
            daily_ingest_by_status.append(
                {
                    "date": key,
                    "completed": int(row["completed"] or 0) if row else 0,
                    "failed": int(row["failed"] or 0) if row else 0,
                    "deleted": int(row["deleted"] or 0) if row else 0,
                    "pending_review": int(row["pending_review"] or 0) if row else 0,
                    "queued": int(row["queued"] or 0) if row else 0,
                }
            )

        hourly_messages = self._fill_hourly_series(
            [{"hour": r["hour"], "value": int(r["cnt"] or 0)} for r in hourly_msg_rows]
        )
        hourly_active_users = self._fill_hourly_series(
            [{"hour": r["hour"], "value": int(r["cnt"] or 0)} for r in hourly_session_rows]
        )

        ingest_by_status = [
            {"label": str(status or "unknown"), "value": int(cnt or 0)}
            for status, cnt in ingest_status_rows
        ]

        hourly_requests: list[dict[str, Any]] = []
        hourly_latency_ms: list[dict[str, Any]] = []
        try:
            import time

            end_ts = int(time.time())
            start_ts = end_ts - 24 * 3600
            async with httpx.AsyncClient(timeout=self._prometheus.timeout) as client:
                req_result = await self._prometheus._query_range(
                    client,
                    "sum(rate(spark_http_requests_total[5m]))",
                    start=start_ts,
                    end=end_ts,
                    step="3600",
                )
                lat_result = await self._prometheus._query_range(
                    client,
                    (
                        "histogram_quantile(0.95, sum by (le) "
                        "(rate(spark_http_request_seconds_bucket[5m])))"
                    ),
                    start=start_ts,
                    end=end_ts,
                    step="3600",
                )
            if req_result:
                values = req_result[0].get("values") or []
                hourly_requests = [
                    {
                        "ts": int(ts),
                        "label": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%H:%M"),
                        "value": round(float(val), 4),
                    }
                    for ts, val in values
                    if val is not None
                ]
            if lat_result:
                values = lat_result[0].get("values") or []
                hourly_latency_ms = [
                    {
                        "ts": int(ts),
                        "label": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%H:%M"),
                        "value": round(float(val) * 1000, 1),
                    }
                    for ts, val in values
                    if val is not None
                ]
        except Exception:
            pass

        return {
            "days": days,
            "daily_active_users": daily_active_users,
            "daily_sessions": daily_sessions,
            "daily_tokens_est": daily_tokens_est,
            "daily_messages": daily_messages,
            "daily_ingest_jobs": daily_ingest_jobs,
            "daily_ingest_by_status": daily_ingest_by_status,
            "daily_token_split": daily_token_split,
            "hourly_messages": hourly_messages,
            "hourly_active_users": hourly_active_users,
            "hourly_requests": hourly_requests,
            "hourly_latency_ms": hourly_latency_ms,
            "ingest_by_status": ingest_by_status,
        }


system_admin_service = SystemAdminService()


async def build_system_admin_dashboard(session: AsyncSession) -> dict[str, Any]:
    return await system_admin_service.fetch_dashboard(session)


async def run_system_admin_action(action: str, *, operator: str, message: str | None = None) -> dict[str, Any]:
    from spark.core.cache import Cache
    from spark.core.readyz_probe import clear_readyz_cache_for_tests
    from spark.workers.tasks_reconcile import reconcile_vectors_task

    if action == "clear-cache":
        deleted = await Cache.get().clear_spark_keys()
        clear_readyz_cache_for_tests()
        return {"ok": True, "action": action, "detail": {"deleted_keys": deleted}}

    if action == "qdrant-sync":
        task = reconcile_vectors_task.delay(factory_id=None, auto_fix=True)
        return {"ok": True, "action": action, "detail": {"task_id": task.id}}

    if action == "reset-agentic":
        return {"ok": True, "action": action, "detail": {"note": "agentic path disabled"}}

    if action == "reset-rag":
        ok = await reset_rag_circuit_manual(operator=operator, reason="system_admin_manual")
        return {"ok": ok, "action": action, "detail": {"reset": ok}}

    if action == "maintenance-on":
        set_maintenance_mode(reason=message or "maintenance", operator=operator)
        return {"ok": True, "action": action, "detail": {"enabled": True}}

    if action == "maintenance-off":
        clear_maintenance_mode()
        return {"ok": True, "action": action, "detail": {"enabled": False}}

    raise ValueError(f"unknown action: {action}")
