# Operations Guide

Running and maintaining a deployed Neo Chat instance: health checks,
configuration profiles, observability, backups, and troubleshooting. For a
step-by-step **installation** walkthrough of the self-hosted factory kit,
see [`deploy/README-ONPREM.md`](../deploy/README-ONPREM.md) instead — this
guide assumes the system is already running and focuses on keeping it
healthy.

## Contents

- [Health checks](#health-checks)
- [Configuration profiles](#configuration-profiles)
- [Observability](#observability)
- [Backups & data safety](#backups--data-safety)
- [Common operational tasks](#common-operational-tasks)
- [Troubleshooting](#troubleshooting)
- [Useful scripts](#useful-scripts)
- [Related docs](#related-docs)

## Health checks

| Endpoint | Use |
| --- | --- |
| `GET /` | Liveness — the process can respond at all |
| `GET /healthz` | Basic liveness probe |
| `GET /readyz?lite=1` | Fast readiness check for Docker/Kubernetes health probes — just Postgres `SELECT 1` + Redis `PING` |
| `GET /readyz` | Full dependency matrix (Postgres, Redis, Qdrant, LLM gateway, storage), cached ~30s in-process |
| `GET /readyz?deep=1` | Same as above but bypasses the cache — use after a deploy or when actively debugging |
| `GET /metrics` | Prometheus exposition format |

An LLM gateway that's degraded is reported inside `/readyz` but **by
design does not flip the overall status to `not_ready`** — the system is
built to keep serving document retrieval and degrade generation gracefully
rather than go fully down over an external dependency. Check the `llm`
field specifically if chat answers are failing but `/readyz` looks green.

The daily/first-boot smoke check:

```bash
curl http://localhost:8000/readyz          # API + core dependencies
open http://localhost:3000                 # or curl -I, confirm the web UI serves
systemctl status spark-gpu-sidecar         # if the GPU sidecar is deployed
docker compose ps                          # confirm postgres/redis/qdrant/minio are healthy
```

When validating a new or changed environment, always follow up with a
real end-to-end check, not just green health probes: upload one small test
document, wait for it to reach `completed`, and ask a question about it —
see the [Handover acceptance checklist](./HANDOVER.md#18-handover-acceptance-checklist)
for the full list.

## Configuration profiles

Neo Chat is driven by environment variables (`.env`, loaded into
`src/spark/core/config.py`'s `Settings` object) plus named **profiles** in
`configs/`:

| Profile type | Config file | Selected via |
| --- | --- | --- |
| LLM / embedding / rerank | `configs/llm_profiles.yaml` (16 profiles) | `LLM_PROFILE` env var |
| Ingestion behavior per document type | `configs/ingestion/<type>.yaml` (13 files) | Automatic, by document type |
| Chunking strategy | `configs/chunking_profiles.yaml` | Per document type, or per-factory override (Admin → Factories → Settings) |
| Retrieval/eval tuning | `configs/eval/*`, `configs/retrieval*` | Used by CI and manual eval runs |
| Compliance / PII policy | `configs/compliance/*` | Ingestion trust scan |

**Production lock**: when `APP_ENV=production` (or `SPARK_PROFILE=production`),
a startup check (`validate_for_production`) fails fast if unsafe defaults
are detected — e.g. a placeholder `JWT_SECRET`, `AUTH_REQUIRED=false`, or a
dev-only LLM profile pointing at `localhost:11434`. If the app refuses to
start in production mode, check this first before assuming something else
is broken.

**A profile pointing at local Ollama will fail on hosts without Ollama** —
profiles like `demo`, `translate_th`, and `rag_th` are dev-only. Production
sites typically use a remote gateway profile instead; confirm which
profile is actually configured with `echo $LLM_PROFILE` on the host, not
just what's in `.env.example`.

## Observability

The core system always exposes `/metrics` and the
[System Admin / Control Room](./admin-guide.md#system-admin--control-room-system-admin)
dashboard — both work with zero extra setup. A fuller stack is available as
an **optional overlay**:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

| Service | Config | Notes |
| --- | --- | --- |
| Prometheus | `ops/prometheus.yml` | Scrapes `/metrics` |
| Grafana | `ops/grafana/` | Dashboards for the metrics below; **default login is `admin`/`admin` — change it immediately if you enable this** |
| Jaeger | — | OpenTelemetry trace viewer; enable with `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317`. Tracing is stub-safe when disabled — nothing breaks if you skip this |

Notable custom metrics worth adding to a dashboard: `spark_sse_connections_active`
/ `spark_sse_connections_rejected_total` (streaming chat load),
`spark_acl_cache_miss_duration_seconds` (permission-check overhead),
`ingest_rows_total`, and RAG latency/timeout counters. The Control Room's
built-in panels ([Admin Guide](./admin-guide.md#dashboard-panels)) cover
most day-to-day needs without Grafana — reach for the Prometheus overlay
when you need history/alerting beyond the live snapshot.

Public exposure via Cloudflare Tunnel is configured under
`ops/cloudflared/` — see
[`docs/public-api-integration.md` §3](./public-api-integration.md#3-exposing-the-api-outside-the-jetson)
for exposing the API safely to an external partner.

## Backups & data safety

| Store | What's backed up | How |
| --- | --- | --- |
| PostgreSQL | Users, documents metadata, chat, feedback, audit — everything except vectors and original files | The `pg-backup` container (base `docker-compose.yml`) runs a daily dump, retaining 7 daily / 4 weekly / 3 monthly copies. `ops/backup.sh` / `ops/restore.sh` are the manual equivalents |
| Qdrant | Vector index | Docker volume (`qdrant_data`) — **must be in your infra backup plan**; losing it means a full re-ingest of every document |
| MinIO / local storage | Original uploaded files, quarantine artifacts, attachments | Docker volume (`minio_data`), or the `data/` directory in local-storage mode — **must be backed up**; losing it means original documents are gone even if metadata survives |

If Qdrant vectors are lost or need rebuilding, use the re-ingest tooling
rather than re-uploading everything by hand:

```bash
python scripts/reconcile_ingest_vectors.py   # fix drift between Postgres and Qdrant counts
python scripts/full_reingest.py              # full re-ingest (dense)
python scripts/full_reingest_v2_sparse.py    # full re-ingest including sparse vectors
python scripts/qdrant_recreate_collections.py
python scripts/ensure_qdrant_indexes.py
```

Reconciliation also runs automatically on a schedule (every 15 minutes) and
can be triggered on demand from the Control Room's **"Sync Qdrant"**
action ([Admin Guide § Actions bar](./admin-guide.md#actions-bar)).

## Common operational tasks

**Restart after a config change**
```bash
# API + worker (compose)
docker compose restart api celery_worker
# or, running directly:
systemctl restart spark-api spark-celery-worker    # unit names vary by install
```

**Re-run a failed ingest job** — from the Upload page's job list (retry
button), or:
```bash
curl -X POST http://localhost:8000/api/v1/ingest/jobs/<job_id>/retry \
  -H "Authorization: Bearer <token>"
```

**Wait for the ingest queue to drain** (useful before a maintenance window):
```bash
python scripts/wait_ingest_idle.py
```

**Remove a broken document and its orphaned vectors**:
```bash
python scripts/cleanup_broken_doc.py --help
```

**Pre-go-live sanity check**:
```bash
bash scripts/go_live_preflight.sh
```

## Troubleshooting

| Symptom | Likely cause | First checks / fix |
| --- | --- | --- |
| Chat returns "AI temporarily unavailable" (`UNAVAILABLE`) | LLM gateway down or quota exhausted | Check the configured gateway's health directly; check quota with the gateway provider; check `/readyz?deep=1`. Consider switching `LLM_PROFILE` to a backup profile |
| Chat returns "no data found" (`NO_DATA`) unexpectedly | Evidence/rerank gate failing, or an embedding-model mismatch | Inspect the message's retrieval snapshot (`GET /chat/{session}/messages/{id}/retrieval-snapshot`); confirm the Qdrant collection actually has vectors for that factory; confirm embedding lineage matches; check whether the RAG circuit breaker is open |
| RAG circuit open | Rolling error-rate threshold tripped | `POST /api/v1/system-admin/actions/reset-rag-circuit`, then investigate the underlying LLM/embedding errors that tripped it |
| Reranking slow or timing out | GPU sidecar or remote rerank gateway down | `curl http://localhost:8137/healthz`; check the sidecar's systemd status. Reranking falls back to fusion scores automatically, so this degrades quality rather than failing the request |
| Ingest job stuck in `pending` | No worker consuming the queue, or a stale lock | Confirm a Celery worker is up and consuming both the default and `ocr_heavy` queues; a scheduled task rescues stuck-pending jobs every 5 minutes, so a brief stall may self-heal |
| Ingest job `quarantined` | Content-safety/PII scan flagged it | Review `GET /documents/{id}/policy-findings`; an admin (not the uploader) releases it — see [Admin Guide § Document release](./admin-guide.md#document-release-quarantine-review) |
| OCR never runs | No worker consuming the `ocr_heavy` queue | Add a worker for that queue, or rely on the inline OCR fallback if enabled |
| Qdrant/Postgres counts drift apart | A write to one store didn't make it to the other | The 15-minute reconciliation job fixes this automatically; force it immediately with the Control Room's "Sync Qdrant" action or `scripts/reconcile_ingest_vectors.py` |
| `/readyz` returns 503 | A critical dependency is down | `GET /readyz?deep=1` reports which dependency specifically; `?lite=1` only checks Postgres+Redis so it can mask a Qdrant/LLM problem |
| Web login fails right after a deploy | `JWT_SECRET` differs between the API and web | The API's `.env` and the web app's `.env.local` must use the **same** `JWT_SECRET` — a mismatch invalidates every session silently |
| Vision/diagram extraction gets truncated | Token limits too low for the profile, or an edge-proxy timeout | Check the vision profile's `max_tokens`/context settings; confirm extraction is streaming (required behind a proxy with a short timeout, e.g. Cloudflare's ~100s edge limit) |

## Useful scripts

| Script | Purpose |
| --- | --- |
| `scripts/go_live_preflight.sh` | Pre-launch sanity checks |
| `scripts/wait_ingest_idle.py` | Block until the ingest queue is empty |
| `scripts/cleanup_broken_doc.py` | Remove a broken document and its orphaned vectors |
| `scripts/reconcile_ingest_vectors.py` | Force a Postgres↔Qdrant reconciliation pass |
| `scripts/full_reingest.py` / `scripts/full_reingest_v2_sparse.py` | Full re-ingest of the document library (with/without sparse vectors) |
| `scripts/qdrant_recreate_collections.py` | Recreate Qdrant collections from scratch |
| `scripts/ensure_qdrant_indexes.py` | Ensure required Qdrant payload indexes exist |
| `scripts/init_db.py` | Initialize/seed a fresh database |
| `ops/backup.sh` / `ops/restore.sh` | Manual Postgres backup/restore helpers |
| `deploy/setup_onprem.sh` | One-click on-prem install (see [`deploy/README-ONPREM.md`](../deploy/README-ONPREM.md)) |

## Related docs

- [docs/HANDOVER.md § 17 Operational runbook](./HANDOVER.md#17-operational-runbook--troubleshooting) — the same troubleshooting table plus the full engineering context around it
- [deploy/README-ONPREM.md](../deploy/README-ONPREM.md) — installing the self-hosted factory kit, performance tuning, and a security checklist
- [gpu-sidecar/README.md](../gpu-sidecar/README.md) — GPU accelerator setup and health check
- [docs/admin-guide.md](./admin-guide.md) — the Control Room dashboard and its operational actions
- [docs/DELIVERY_ACCEPTANCE.md](./DELIVERY_ACCEPTANCE.md) — credential rotation procedure, warranty/support windows
