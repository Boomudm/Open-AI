"""Query Prometheus (Grafana datasource) for Neo Chat overview metrics."""

from __future__ import annotations

import math
import time
from typing import Any

import httpx

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

# Mirrors ops/grafana/dashboards/spark-overview.json panel queries.
INSTANT_QUERIES: dict[str, str] = {
    "requests_per_sec": "sum(rate(spark_http_requests_total[1m]))",
    "p95_latency_sec": (
        "histogram_quantile(0.95, sum by (le) (rate(spark_http_request_seconds_bucket[5m])))"
    ),
}

RANGE_QUERIES: dict[str, str] = {
    "embedding_p95": (
        "histogram_quantile(0.95, sum by (le) (rate(spark_embedding_seconds_bucket[5m])))"
    ),
    "embedding_p50": (
        "histogram_quantile(0.50, sum by (le) (rate(spark_embedding_seconds_bucket[5m])))"
    ),
    "rag_scope_broadened": "sum by (fallback_level) (rate(spark_rag_scope_broadened_total[5m]))",
    "rag_query_volume": "sum by (fallback_level) (rate(spark_rag_query_total[5m]))",
    "rag_fallback": "sum by (fallback_level) (rate(spark_rag_scope_broadened_total[5m]))",
    "ingest_rows": "sum by (outcome) (rate(spark_ingest_rows_total[5m]))",
}


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return value


def _parse_scalar(result: list[dict[str, Any]]) -> float | None:
    if not result:
        return None
    try:
        return _safe_float(float(result[0]["value"][1]))
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _parse_series(result: list[dict[str, Any]]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for item in result:
        metric = item.get("metric") or {}
        label = (
            metric.get("fallback_level")
            or metric.get("outcome")
            or metric.get("__name__")
            or "value"
        )
        points = [
            {"ts": int(ts), "value": v}
            for ts, val in item.get("values") or []
            if (v := _safe_float(float(val))) is not None
        ]
        if points:
            series.append({"label": str(label), "points": points})
    return series


class ObservabilityService:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")
        self.timeout = timeout

    async def _query(self, client: httpx.AsyncClient, expr: str) -> list[dict[str, Any]]:
        resp = await client.get(
            f"{self.base_url}/api/v1/query",
            params={"query": expr},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "success":
            raise RuntimeError(body.get("error", "prometheus query failed"))
        return body.get("data", {}).get("result") or []

    async def _query_range(
        self,
        client: httpx.AsyncClient,
        expr: str,
        *,
        start: int,
        end: int,
        step: str = "30s",
    ) -> list[dict[str, Any]]:
        resp = await client.get(
            f"{self.base_url}/api/v1/query_range",
            params={"query": expr, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "success":
            raise RuntimeError(body.get("error", "prometheus range query failed"))
        return body.get("data", {}).get("result") or []

    async def fetch_overview(self, *, range_minutes: int = 60) -> dict[str, Any]:
        end = int(time.time())
        start = end - range_minutes * 60
        overview: dict[str, Any] = {
            "source": "prometheus",
            "prometheus_url": self.base_url,
            "grafana_dashboard_uid": "spark-overview",
            "available": False,
            "stats": {},
            "series": {},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for key, expr in INSTANT_QUERIES.items():
                    result = await self._query(client, expr)
                    overview["stats"][key] = _parse_scalar(result)

                embedding: list[dict[str, Any]] = []
                for label, expr in (
                    ("p95", RANGE_QUERIES["embedding_p95"]),
                    ("p50", RANGE_QUERIES["embedding_p50"]),
                ):
                    result = await self._query_range(client, expr, start=start, end=end)
                    for s in _parse_series(result):
                        s["label"] = f"embedding {label}"
                        embedding.append(s)
                overview["series"]["embedding_latency"] = embedding

                rag_result = await self._query_range(
                    client, RANGE_QUERIES["rag_fallback"], start=start, end=end
                )
                overview["series"]["rag_fallback"] = _parse_series(rag_result)

                ingest_result = await self._query_range(
                    client, RANGE_QUERIES["ingest_rows"], start=start, end=end
                )
                overview["series"]["ingest_rows"] = _parse_series(ingest_result)

            overview["available"] = True
        except Exception as exc:
            log.warning("observability_fetch_failed", error=str(exc)[:200])
            overview["error"] = str(exc)[:240]

        return overview


observability_service = ObservabilityService()
