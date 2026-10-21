# App-layer load smoke (Phase 11)

Run on the factory LAN **before pilot cutover** to validate multi-worker API health under light concurrent load.

## Prerequisites

- Stack up: `docker compose -f deploy/docker-compose.onprem.yml --env-file deploy/.env up -d`
- `ONPREM_API_WORKERS` ≥ 2 (default in `deploy/.env.onprem.example`)
- Redis healthy (`docker compose … exec redis redis-cli ping`)

## Run

From repo root:

```bash
# Through nginx (recommended — matches operator path)
uv run python scripts/load/app_layer_smoke.py --base-url http://spark.lan

# Direct API (dev laptop)
uv run python scripts/load/app_layer_smoke.py --base-url http://localhost:8000
```

Options:

| `--scenario` | `healthz` | `healthz`, `sse-rest`, `ticket-mint`, or `all` |
| `--requests` | 50 | Total `/healthz` probes (healthz scenario) |
| `--concurrency` | 20 | Parallel clients |
| `--p95-ms` | 500 | Fail if p95 latency exceeds this (ms) |
| `--sse-count` | 100 | Long-lived alert SSE connections (`sse-rest`) |
| `--rest-concurrency` | 20 | Concurrent `/healthz` probes during SSE hold |
| `--ticket-mints` | 50 | Concurrent `POST /api/v1/streams/ticket` (`ticket-mint`) |
| `SMOKE_BEARER_TOKEN` | — | JWT for SSE/ticket scenarios (login admin in pilot) |

## Baseline (reference hardware)

Recorded on a 8-core / 16GB pilot VM with 2 API workers:

| Metric | Typical |
|--------|---------|
| `/readyz` | 200, `redis.ok=true` |
| `/healthz` p50 | &lt; 50 ms |
| `/healthz` p95 | &lt; 200 ms |
| Failures | 0 |

Re-run after changing `ONPREM_API_WORKERS`, Postgres pool, or nginx rate limits.

## Metrics / docs access

`/metrics` is **admin-LAN only** at nginx (`deploy/nginx/conf.d/spark.conf`) — use VPN or ops workstation on `10.0.0.0/8`, `172.16.0.0/12`, or `192.168.0.0/16`.

`/docs`, `/redoc`, and `/openapi.json` are **public** (no auth).
