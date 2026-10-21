# Neo Chat — Project Handover

> **Repository:** `CPF-Chula-CEDT-2026/spark` · **Internal package name:** `spark` · **Product name:** Neo Chat
> **Version:** 1.0.0 · **Handover doc last verified against code:** 2026-07-20 (branch `main`)
> **Repo history:** on 2026-07-18, all pre-existing git tags and GitHub releases were removed for inconsistent numbering and `main` was reset to `develop`; old tag→commit mapping: `docs/archive/release-tags-2026-07-18.md`. On 2026-07-20 the repo was cut over to 1.0.0 and consolidated to two branches, `main` and `develop` — feature and archive branches are deleted once merged. `CHANGELOG.md` is the release history of record; versioning policy: `CONTRIBUTING.md` → “Versioning & releases”.
>
> This document is written **from the code, configuration, and git history** — not from older docs.
> Where an older doc in this repo disagrees with this one, trust the code and this document.
>
> For delivery scope, acceptance tests, warranty/support terms, liability, and the formal sign-off
> package, see [`docs/DELIVERY_ACCEPTANCE.md`](./DELIVERY_ACCEPTANCE.md) — this file covers the
> engineering "how it works" side; that one covers the commercial "what does delivered mean" side.

---

## Executive summary

Neo Chat (internal code name: `spark`) is an **AI document Q&A system for
factories**, running on-prem/on the LAN. Employees upload documents
(machine manuals, SOPs, HR policy, circuit diagrams, etc.); the system
processes and indexes them, and users can ask questions in Thai or English
and get answers with **source citations**, grounded only in the real
documents (no guessing, no fabricated data).

- **Status:** live in production at `https://neospark.kcalsion.com`
  (running on an NVIDIA Jetson AGX Orin)
- **The system's "brain" (LLM):** routed through an external gateway — chat
  uses `deepseek-v4-flash` (KKU gateway), embedding uses `bge-m3` (runs
  locally), rerank uses ForgeNode. These gateways **remain usable** after
  handover
- **Core technology:** FastAPI (Python), Next.js (web), Celery (background
  jobs), PostgreSQL, Redis, Qdrant (vector DB), MinIO (file storage)
- **Watch out for at handover:** all credentials must be rotated — see
  [15. Credentials & Secrets Inventory](#15-credentials--secrets-inventory) —
  a GitHub token that had leaked into this machine's git remote URL **was
  already removed from the URL (Jul 17)**, but the token itself still needs
  to be **revoked on GitHub**

---

## Table of contents

1. [What Neo Chat is](#1-what-neo-chat-is)
2. [System architecture](#2-system-architecture)
3. [Repository & code map](#3-repository--code-map)
4. [Runtime configuration & profiles](#4-runtime-configuration--profiles)
5. [The RAG / answer pipeline](#5-the-rag--answer-pipeline)
6. [The ingestion pipeline](#6-the-ingestion-pipeline)
7. [Data model](#7-data-model)
8. [API surface](#8-api-surface)
9. [Authentication, authorization & trust](#9-authentication-authorization--trust)
10. [Frontend (Next.js)](#10-frontend-nextjs)
11. [Background workers & scheduled jobs](#11-background-workers--scheduled-jobs)
12. [Deployment & operations](#12-deployment--operations)
13. [Local development setup](#13-local-development-setup)
14. [Testing & quality gates](#14-testing--quality-gates)
15. [Credentials & secrets inventory](#15-credentials--secrets-inventory)
16. [Known limitations, risks & roadmap](#16-known-limitations-risks--roadmap)
17. [Operational runbook & troubleshooting](#17-operational-runbook--troubleshooting)
18. [Handover acceptance checklist](#18-handover-acceptance-checklist)
19. [Glossary & further reading](#19-glossary--further-reading)

---

## 1. What Neo Chat is

Neo Chat is an **on-prem, document-grounded RAG (Retrieval-Augmented Generation) chat system** for
factory knowledge. The single core workflow is:

1. **Upload** PDF, Word, Excel, image, text, or Markdown documents (per document type).
2. **Ingest & index** them into PostgreSQL (metadata + lexical text) and Qdrant (dense + sparse vectors).
3. **Ask** questions in Thai or English and receive answers **grounded in and cited from** those documents.
4. **Manage** users, job-position document access, feedback, document releases, and factory config.

It is explicitly built to **fail closed**: if the system cannot find sufficient evidence, it answers
`ไม่พบข้อมูลในระบบ กรุณาติดต่อวิศวกร` ("no data in system, contact an engineer") rather than
hallucinating. This is a hard product constraint that runs through the whole retrieval/generation code.

### Product surface (user-facing routes)

| Route | Purpose |
|-------|---------|
| `/chat` | Document-grounded Q&A with live streaming answer, "thinking" timeline, and citations. **Primary workspace** — `/` redirects here. |
| `/documents` | Browse, open, and re-ingest indexed documents |
| `/upload` | Upload documents and monitor ingest jobs (live progress via SSE) |
| `/machines` | Machine browsing and CRUD |
| `/admin` | Users, job positions, document access, feedback review, external data sources |
| `/dashboard` | Analytics / KPIs |
| `/system-admin` | NOC-style control-room dashboard (traffic, latency, ingest, incidents) |
| `/account`, `/login`, `/signup`, `/privacy`, `/auth/callback` | Account & auth flows (password + Google OAuth) |
| `/feedback` | Knowledge feedback submission & review |

### Domain vocabulary

- **Factory** (`factory_id`, e.g. `F-01`, `E-03`) — top-level tenant/scope. Almost everything is
  scoped by factory. RBAC, Qdrant sharding, and rate limits all key on factory.
- **Machine** / **Component** — factory equipment hierarchy; documents and questions can be scoped to a machine.
- **Job position** — controls which documents a user may see (document-access ACL keys on job positions).
- **Document type** — one of 13 ingestion profiles (see §6) that drive parsing, chunking, and routing.

---

## 2. System architecture

### 2.1 Component overview

```
                          ┌────────────────────────────────────────────────┐
   Browser (operator) ───►│ Next.js 14 web UI  (web/, port 3000)            │
                          │  - React Query, Zustand, SSE chat streaming     │
                          └───────────────┬────────────────────────────────┘
                                          │  HTTP + SSE  (via nginx / Cloudflare tunnel)
                          ┌───────────────▼────────────────────────────────┐
                          │ FastAPI API  (src/spark, uvicorn :8000)         │
                          │  - api/v1 routers (~101 routes)                 │
                          │  - platform middleware: auth, rate limit, CORS, │
                          │    security headers, trusted-proxy, SSE gov.    │
                          │  - ChatOrchestrator → RAG / Enterprise / SQL    │
                          └──┬───────────┬──────────┬───────────┬───────────┘
                             │           │          │           │
                  ┌──────────▼──┐ ┌──────▼─────┐ ┌──▼───────┐ ┌─▼─────────────┐
                  │ PostgreSQL  │ │  Qdrant    │ │  Redis   │ │  MinIO (S3)   │
                  │ (metadata,  │ │ (dense +   │ │ (cache,  │ │ (document     │
                  │  lexical    │ │  sparse    │ │  Celery  │ │  blob store)  │
                  │  FTS, audit)│ │  vectors)  │ │  broker) │ │               │
                  └─────────────┘ └────────────┘ └────┬─────┘ └───────────────┘
                                                      │ broker
                          ┌───────────────────────────▼────────────────────┐
                          │ Celery workers (spark.workers)                  │
                          │  - default queue: ingest pipeline               │
                          │  - ocr_heavy queue: OCR of scanned PDFs         │
                          │  - celery beat: reconcile, purge, cleanup       │
                          └───────────────┬─────────────────────────────────┘
                                          │ HTTP
        External LLM / embedding / rerank backends (see §4):
        ┌─────────────────────────┬──────────────────────────┬─────────────────────────┐
        │ KKU gateway             │ ForgeNode                │ kcalsion gateway        │
        │ gen.ai.kku.ac.th        │ forge.kcalsion.com       │ api.kcalsion.com        │
        │ chat: deepseek-v4-flash │ rerank: Qwen3-Reranker   │ chat: qwen3.6:35b-a3b   │
        └─────────────────────────┴──────────────────────────┴─────────────────────────┘
        ┌──────────────────────────────────────────────────────────────────────────────┐
        │ GPU sidecar (gpu-sidecar/, host Python 3.8 + JetPack CUDA, :8137)             │
        │  embeds bge-m3 + reranks bge-reranker-v2-m3 on the Jetson GPU (fallback path) │
        └──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 The three answer pipelines

`ChatOrchestrator` (`src/spark/services/chat_orchestrator.py`) is the brain of every chat turn. After
routing a question it dispatches to one of several pipelines:

1. **Machinery pipeline** — the main RAG path over machine manuals, SOPs, drawings, datasheets, etc.
   (Qdrant `spark_docs` collection family). This is the default and most-developed path.
2. **Enterprise / "HR Buddy" pipeline** — RAG over enterprise documents (`company_policy`,
   `hr_handbook`, `internal_guideline`) in the `spark_enterprise_docs` collection.
3. **External SQL (Text-to-SQL)** — for analytic questions, routes to a live external Postgres data
   source registered by an admin (`ExternalAnalyticsService`). Supports **compound** questions
   (SQL part + document part merged into one answer).
4. **Chitchat** — greetings/identity handled directly without retrieval.
5. **Agentic canary** — an experimental parallel-tool agent path served to a small % of sessions when
   enabled (`should_serve_agentic`), with a safety override that falls back to the legacy path.

**Routing** is a cascade (see `_route_question_scope`): deterministic chitchat → explicit enterprise
scope → single-sided keyword hint (cheap fast path) → **one context-aware LLM "scope judge"** → sticky
prior scope → default to machinery. A locked machine forces the machinery pipeline.

### 2.3 Request flow (a chat question)

```
POST /api/v1/chat/sessions/{id}/ask  (or the streaming SSE variant)
  → auth middleware resolves Principal (JWT / stream ticket / demo)
  → ChatOrchestrator.ask() / ask_stream()
      → merge session slots + request filter (machine lock, revision, factory)
      → resolve routing + intent (rule + optional LLM router)
      → contextualize question (follow-up rewrite from history)
      → try external analytics (Text-to-SQL) if analytic
      → route scope (chitchat / enterprise / machinery)
      → RAGService.query() / query_stream():   [machinery / enterprise]
            RAGKernel entry guardrails (query policy, safety intent, circuit breaker)
            → hybrid retrieval: dense (bge-m3) + lexical (Postgres Thai FTS) → RRF fusion
            → cross-encoder rerank (bge-reranker-v2-m3) + absolute relevance gate
            → evidence gates (lexical / extractive / safety-specific)
            → generation: CRAG verify → grounded LLM → NLI gate → self-verify → citation enforce
            → fail-closed to NO_DATA / extractive span / flagged-unverified as appropriate
      → persist user + assistant ChatMessage, update session slots + title
      → record audit + question analytics
  → response (answer, sources[], confidence tier, retrieval report, degradation)
```

---

## 3. Repository & code map

```
spark/
├── src/spark/                  FastAPI backend (the core system)
│   ├── main.py                 App factory, lifespan (migrations, startup checks), health endpoints
│   ├── api/                    HTTP layer
│   │   ├── v1/endpoints/       ~22 routers (auth, chat, ingest, documents, admin, machines, ...)
│   │   ├── v1/router.py        Router aggregation (prefix /api/v1)
│   │   └── platform/           Middleware stack, error handlers, rate limit, SSE policy, trusted proxy
│   ├── core/                   Config, DB, cache, auth, security, qdrant, llm_client, profiles, metrics
│   ├── services/               Business logic (chat_orchestrator, rag_service facade, external_sql, ...)
│   ├── retrieval/              RAG retrieval engine (hybrid search, fusion, rerank, gates, safety)
│   ├── generation/             Answer generation (grounded LLM, NLI gate, self-verify, citations)
│   ├── ingestion/              Ingest pipeline (parsers, chunking, trust/PII, indexing, generation swap)
│   ├── workers/                Celery app + tasks (ingest, OCR, reconcile, purge, policy rescan)
│   ├── db/models/              SQLAlchemy ORM models (32 tables)
│   ├── schemas/                Pydantic request/response schemas + OpenAPI examples
│   ├── compliance/             Data classification / PII policy
│   ├── audit/                  Audit event helpers
│   ├── integrations/           DeepAnalyze, predictive (heuristic) integrations
│   └── observability/          OTel tracing stubs + metrics
├── web/                        Next.js 14 frontend (app router)
│   ├── app/                    Routes (chat, documents, upload, admin, machines, dashboard, ...)
│   ├── components/             React components grouped by feature
│   ├── lib/                    API clients, chat streaming, auth, i18n, offline, speech, trust
│   ├── stores/                 Zustand stores (chatStore, uiStore)
│   └── e2e/                    Playwright end-to-end tests
├── configs/                    YAML/JSON config: LLM & embedding profiles, ingestion per-doc-type,
│                               retrieval tuning, eval suites, compliance taxonomy, production locks
├── alembic/versions/           58 DB migrations (latest: 0059_api_keys)
├── deploy/                     On-prem deployment kit (docker-compose.onprem, nginx, jetson, setup script)
├── gpu-sidecar/                Standalone GPU inference sidecar (host py3.8 + JetPack torch)
├── ops/                        Prometheus, Grafana, nginx, cloudflared operational config
├── scripts/                    ~70 operational/dev/eval scripts (init_db, reingest, eval gates, jetson, ...)
├── tests/                      Python test suite (unit, contracts, chaos, compliance, retrieval, ...)
├── docs/                       Documentation (this file is the authoritative handover)
├── models/, assets/, data/     Model cache, static assets, runtime data (data/ is root-owned on server)
├── docker-compose*.yml         Compose stacks (base infra, dev-app, prod, observability, gpu, factory, ...)
└── pyproject.toml              Python deps (uv-managed), ruff, pytest config
```

### Key architectural notes

- **Vertical slices with facades.** `services/rag_service.py` is a thin compatibility facade; the real
  retrieval logic lives under `spark.retrieval` and generation under `spark.generation`. New code should
  import from the vertical slices directly (see `docs/architecture/import_spine_v2.md`).
- **`retrieval/service.py` (~2,300 lines)** is the core `RAGService` with `query()`, `query_stream()`,
  and `_resolve_retrieval()`. `retrieval/kernel.py` wraps both sync and stream through one set of entry
  guardrails (query policy scan, safety-intent detection, circuit-breaker decision).
- **Ingestion is a staged, streaming pipeline.** `ingestion/pipeline.py` → `stages/runner.py` →
  `orchestrator.run_streaming_pipeline()`. Parsing streams row-by-row so large binders don't blow memory.

---

## 4. Runtime configuration & profiles

### 4.1 The `Settings` object

All runtime config is centralized in `src/spark/core/config.py` (`Settings`, a pydantic-settings
`BaseSettings`). It reads from the repo-root `.env` and environment variables. Highlights:

- `app_env` — `development` | `production`. Production hard-enforces auth and forbids demo LLM/insecure JWT.
- `spark_profile` — `test` | `production` | `dev`. `test` relaxes security gates for CI; production/dev are hardened.
- `llm_profile` — selects an entry in `configs/llm_profiles.yaml` (see §4.3).
- Database, Redis, Qdrant connection settings; storage backend (`local` | `s3`).
- Extensive RAG tuning knobs (rerank candidate caps, evidence floors, budgets, circuit-breaker thresholds).

**Startup validation** (`main.py` lifespan) is strict and fail-fast: `validate_for_production()`,
`validate_profile_env()`, `validate_app_profile()`, ingest-contract validation, production-lock
validation, GPU-rerank gate validation, and a set of async startup checks. Misconfiguration in
production raises at boot rather than silently degrading.

### 4.2 Current production `.env` (the canonical live config on the Jetson)

The receiving team keeps this setup. Non-secret values from the live `.env` (secrets redacted):

```ini
APP_ENV=production
SPARK_PROFILE=production
SPARK_LAYOUT_PARSER=docling            # production PDF layout parser (docling); fallback_pypdf for dev
LLM_PROFILE=kku_gemini                 # chat=deepseek-v4-flash, embed=bge-m3 local, rerank=forge
FORGE_BASE_URL=https://forge.kcalsion.com
FORGE_RERANK_ENABLED=true
OLLAMA_LLM_MODEL=qwen3.6:35b-a3b       # informational; active model comes from the profile
OLLAMA_EMBED_MODEL=bge-m3
OLLAMA_EMBED_DIM=1024
AUTH_REQUIRED=true
CORS_ORIGINS=http://spark.lan,http://localhost:3000,https://neospark.kcalsion.com
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://127.0.0.1:9000  # MinIO on the box
S3_BUCKET=spark-documents
GPU_SIDECAR_REQUIRED=false
NEXT_PUBLIC_SPARK_API_URL=http://spark-api.lan
WEB_APP_URL=https://neospark.kcalsion.com
GOOGLE_CLIENT_ID=729076132054-...apps.googleusercontent.com
GOOGLE_OAUTH_CALLBACK_URL=https://neospark.kcalsion.com/api/v1/auth/google/callback
GOOGLE_OAUTH_ALLOWED_DOMAINS=kcalsion.com,gmail.com
GOOGLE_OAUTH_DEFAULT_ROLE=viewer
GOOGLE_OAUTH_DEFAULT_FACTORY_ID=E-03
INGEST_BACKEND=native
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

The full annotated template is `.env.example` (9 KB, every variable documented). Deployment-specific
templates: `.env.factory.example`, `.env.kcalsion.example`, `deploy/.env.onprem.example`,
`deploy/jetson/.env.jetson.example`.

### 4.3 LLM / embedding / rerank backends

Backends are defined in `configs/llm_profiles.yaml`. This is the **most operationally important config
file** — it decides which model serves chat, embeddings, and reranking. Key profiles:

| Profile | Chat model | Chat endpoint | Embeddings | Rerank |
|---------|-----------|---------------|-----------|--------|
| **`kku_gemini`** ⭐ *(current prod)* | `deepseek-v4-flash` | `gen.ai.kku.ac.th` (KKU) | `bge-m3` local (sentence_transformers) | ForgeNode `Qwen3-Reranker-0.6B` |
| `gemma_remote` | `qwen3.6:35b-a3b` | `api.kcalsion.com` | `bge-m3` local | `bge-reranker-v2-m3` |
| `forge_remote` | `qwen3.6:35b-a3b` | `forge.kcalsion.com` | ForgeNode `bge-m3` | ForgeNode reranker |
| `gemma` | `qwen3.6:35b-a3b` | on-box proxy `:9090` (via `host.docker.internal`) | `bge-m3` local | `bge-reranker-v2-m3` |
| `vision_extract` | `qwen3-vl:4b` (vision) | `api.kcalsion.com` | `bge-m3` local | — |
| `tagging` / `judge` | `deepseek-v4-flash` | KKU | `bge-m3` local | — |
| `demo` | `qwen2.5:3b-instruct` | local Ollama `:11434` | `bge-m3` local | — |
| `prod` | `Qwen/Qwen2.5-14B-Instruct` | local vLLM `:8001` | `bge-m3` local | `bge-reranker-v2-m3` |

**Critical embedding invariant:** the standard embedder across all profiles is **`BAAI/bge-m3`,
1024-dim**, L2-normalized, cosine in Qdrant. **Switching embedding model/provider requires a full
re-ingest** (Qdrant collections are rebuilt at 1024-dim; `qdrant_router` asserts dims). Vectors from
`bge-m3` are identical whether produced locally (sentence_transformers), by the GPU sidecar, or by
ForgeNode — so the resilient embed **ladder** (ForgeNode → Jetson GPU sidecar → CPU) is transparent to
already-indexed data.

**Why `kku_gemini` is the current prod choice** (from the config comments and CHANGELOG): the
`qwen3.6:35b-a3b` model on the kcalsion/forge gateways is slow (~20 s single call, times out at ~3
concurrent) and ForgeNode had a Cloudflare 502 outage; KKU's `deepseek-v4-flash` (originally
`gemini-2.5-flash`, swapped after hitting the KKU daily token quota) is fast and high-concurrency.
Embeddings + reranker stay on the local/Forge `bge-m3` lineage so **no re-ingest is needed** when the
chat model changes. Note: `qwen3.6:35b-a3b` on kcalsion extracts exact spec/alarm values better and is
the recommended generation model when a valid session token / capacity is available.

⚠️ **KKU daily token quota** (~350k tokens/day observed) is enforced per key — watch it under heavy RAG
load. Chat degrading to `UNAVAILABLE_ANSWER` ("ระบบ AI ไม่พร้อมชั่วคราว") is a common symptom of quota
exhaustion or a down gateway.

### 4.4 GPU sidecar

The **GPU sidecar** (`gpu-sidecar/`) exists because this is a JetPack 5.1 / CUDA 11.4 Jetson: the only
working GPU PyTorch is the JetPack build for **Python 3.8**, but the app needs Python ≥3.11, so GPU
torch cannot live in the app container. The sidecar is a tiny FastAPI service (`/embed`, `/rerank`,
`/healthz`) on the host at `:8137` that runs `bge-m3` and `bge-reranker-v2-m3` on the GPU. Measured:
rerank of 34 chunks went 20–80 s (CPU, timing out) → ~0.6 s (GPU); query embed 340 ms → 66 ms.

- The app reaches it via `GPU_SIDECAR_URL` (e.g. `http://host.docker.internal:8137`).
- The app **falls back to in-process CPU models on any sidecar failure** — it never hard-depends on it,
  unless `GPU_SIDECAR_REQUIRED=true` (fail-closed on Jetson prod boxes).
- Installed as a systemd unit `spark-gpu-sidecar.service` (survives reboot). See `gpu-sidecar/README.md`.

---

## 5. The RAG / answer pipeline

This is the heart of the product. Code lives in `src/spark/retrieval/` and `src/spark/generation/`.

### 5.1 Entry guardrails (`retrieval/kernel.py`)

Both sync and streamed queries pass through `RAGKernel._apply_entry_guardrails`:

1. **Query policy scan** (`safety/query_policy.py`) — blocks disallowed queries → `NO_DATA` fail-closed.
2. **Safety-intent detection** (`safety/safety_intent.py`) — detects LOTO / SOP / equipment-safety
   intents; these require **strict retrieval** (stricter gates, no scope broadening).
3. **Circuit-breaker decision** (`retrieval/circuit/`, `safety/circuit_breaker.py`) — a per-factory
   circuit that, when open, can skip the LLM (`skip_llm`), force degraded rerank, or fail closed on the
   embed breaker. Driven by rolling error-rate thresholds (LLM timeout rate, embed error rate, rerank
   gate-fail rate) over a 600 s window, persisted to a flag file.

### 5.2 Hybrid retrieval

- **Dense leg:** query embedded with `bge-m3` (1024-dim) → Qdrant cosine search over the factory's
  collection(s). Multi-query expansion (`rag_multi_query_expansion`) also runs the dense leg with the
  Thai→EN glossary-expanded query and fuses both — this recovers Thai questions whose answers live in
  English-only manuals (a core cross-lingual feature).
- **Lexical leg:** PostgreSQL Thai full-text search v3 (`retrieval/lexical/postgres_thai_v3.py`) with
  `pythainlp` tokenization + `pg_trgm` prefilter. Industrial + Thai tokenizers handle mixed
  Thai/English/part-number text.
- **Fusion:** Reciprocal Rank Fusion (`retrieval/fusion.py`, `rag_rrf_k=60`) merges dense + lexical.

**Wiring-diagram query understanding (2026-07-16).** Technicians ask about drawings by device tag,
terminal, or rail — never by the word "diagram" — so the query side understands that phrasing natively:

- `lexical/tokenize_industrial.py` extracts IEC device designators from a closed prefix set (`K1`,
  `CB1`, `MCB2`, `X1`, `F2`, `R3`, …), `Tag:Terminal` refs exactly as the vision connection tables
  print them (`X1:5`, `M18:GND` — the device half is emitted too), power/ground rails (`24VDC`,
  `0V`, `GND`, `PE`, `L1`–`L3`), and all-caps hyphenated model codes with no digits (`AZD-KEP`).
  One extractor feeds three legs at once: exact-match terms, index-time `boost_tokens`
  (`ingestion/index/lexical_enrich.py`, limit raised to 48 so short tags survive the cap), and the
  answerability evidence terms. Existing ingests keep their old `boost_tokens` until reingested —
  the exact and sparse legs already match the new tokens against chunk text, so this degrades soft.
- `intent/features.py:has_wiring_connectivity_terms` routes connectivity/impact/location questions
  ("M18 ต่อกับอะไร", "ถ้า K1 เสีย กระทบอะไร", "M17 อยู่ในแบบหน้าไหน") to a **soft drawing route**
  (`drawing_connectivity` in `intent_weights_v2.yaml`): drawing rank-prior + lexical-heavy weights but
  **no strict document filter**, because manuals may legitimately carry the answer. Explicit
  "wiring diagram" questions keep the strict `drawing` route.
- `retrieval/exact.py` normalizes spoken terminal phrases ("X1 ขา 5", "CN1 pin 3") into the `X1:5`
  form the tables use; `intent/glossary.py` bridges Thai electrical vocabulary (เทอร์มินอล, กราวด์,
  รีเลย์, คอนแทคเตอร์, …) onto the Latin labels the vision analyses keep.
- `generation/prompts.py` rule 11 has a carve-out: page numbers that are *content* (the device index's
  "อุปกรณ์ → หน้าที่พบ" table, cross references) are quotable with a citation, so "อยู่แบบหน้าไหน"
  is answerable; rule 12 shapes wiring answers as location → connections (Tag:Terminal + net) → shared
  buses/failure impact. Tests: `tests/retrieval/test_wiring_diagram_query.py`.

### 5.3 Reranking & gates

- **Cross-encoder rerank** (`retrieval/rerank/`, `BAAI/bge-reranker-v2-m3`, max_len 1024) scores each
  candidate for relevance. Runs on the GPU sidecar or ForgeNode; degrades to fusion scores if unavailable.
  Candidate count capped by `rag_rerank_max_candidates=64`.
- **Absolute relevance gate** — the pipeline always runs dense + lexical → RRF → cross-encoder →
  **absolute gate**. Thresholds (`retrieval/constants.py`), tightened for safety intents:

  | Gate | Value | Meaning |
  |------|-------|---------|
  | `MIN_RERANK_SCORE` | 0.35 | max relevance across retained docs must clear this |
  | `MIN_RERANK_AVG_SCORE` | 0.25 | mean of top-3 relevances must clear this |
  | `MIN_RELEVANT_DOC_SCORE` | 0.35 | a doc is "relevant" above this |
  | `MIN_EXTRACTIVE_EVIDENCE_SCORE` | 0.22 | span-level extractive floor |
  | `MIN_EVIDENCE_SCORE` | 0.18 | general evidence floor |
  | `SAFETY_LOTO_MIN_MAX / _AVG` | 0.45 / 0.35 | stricter for LOTO safety questions |
  | `SAFETY_SOP_MIN_MAX / _AVG` | 0.40 / 0.30 | stricter for SOP safety questions |

- **Weak-evidence continuation** (`rag_weak_evidence_min_score=0.15`): a non-safety question that fails
  the lexical evidence gate still proceeds to generation when the best candidate clears this floor —
  the generation-side gates then decide whether to show the answer verified, flagged, or suppressed.

### 5.4 Generation & grounding gates (`generation/pipeline.py`)

For document answers the generation stage is a sequence of grounding checks — each can downgrade or
suppress the answer:

1. `build_grounded_context` from retrieved docs.
2. **Structured safety** path for safety intents (`constrained_safety.py`) — structured, verified output.
3. **CRAG verify** (`safety/retrieval_verifier.py`) — corrective-RAG relevance check (LLM-judged for
   safety questions; heuristic otherwise, deliberately softened for cross-lingual Thai↔English).
4. **Grounded LLM** (`grounded_llm.py`) — the actual answer generation with citation enforcement.
5. **NLI gate** (`nli_gate.py`) — natural-language-inference entailment check of answer vs. context.
6. **Self-verify** (`self_verify.py`) — a second-pass confidence check; low confidence → `flag_or_suppress`.
7. **Citation enforcement** — answers must cite their sources; uncited/hallucinated-number answers are
   caught (`_answer_has_hallucinated_numbers`, `_ensure_answer_citations`).

Terminal answer paths seen by the orchestrator: `grounded_llm`, `grounded_extractive`,
`grounded_paraphrase`, `grounded_structured_safety`, `qa_cache_hit`, `agentic` (verified) vs.
`no_data`, `llm_unavailable`, `numeric_grounding_fail`, `nli_gate_fail` (unverified/suppressed).

The streamed path shows **provisional tokens** immediately (product decision 2026-07) and then replaces
them with the citation-verified text once validation completes; SSE `stream_phase` reports
searching/reading/generating.

### 5.5 Cross-lingual behavior (a defining feature)

Thai questions over English-only manuals are first-class. When evidence exists only in English, the
system serves **cited extractive spans** (translated to Thai when possible via the `translate_th`
profile) rather than failing closed. The evidence gate has learned equipment-spec/safety vocabulary
(enabling switch, HWTO/EDM, LED/system board). The scope judge and answer language are Thai-aware
(`_thai_ratio`, `_answer_too_english_for_thai_question`).

### 5.6 Performance & safety knobs (from `config.py`)

- `rag_request_budget_ms=150000` — total per-question budget. **Sized for the real hardware** (35B
  gateway / Jetson-class p95 ~120 s); a budget the hardware can't meet silently drops the lexical leg
  and rerank on every question. Do not lower this blindly.
- `rag_llm_timeout_sec=120` (must fit inside the request budget), `rag_lexical_budget_ms=5000`.
- `rag_inflight_max_global` — global concurrent-RAG cap across all factories. The LLM backend is
  shared, so a small global cap turns a silent 90 s timeout into a fast, retryable 429
  (`rag_at_capacity`). Currently `0` (disabled) in defaults; **consider raising for the shared remote
  gateway** (this was a known concurrency-collapse risk — see §16).
- QA cache and semantic cache are **off by default** (`qa_cache_enabled=false`,
  `semantic_cache_enabled=false`).

---

## 6. The ingestion pipeline

Code: `src/spark/ingestion/`. Entry: `ingestion/pipeline.py` → `stages/runner.py:run_staged_pipeline`
→ `orchestrator.run_streaming_pipeline`. Runs inside Celery workers.

### 6.1 Document types (13)

Each type has a config in `configs/ingestion/<type>.yaml` that drives parser selection, chunking
profile, routing (Qdrant / Postgres / both), validation, and trust policy:

`company_policy`, `hr_handbook`, `internal_guideline` (enterprise) · `machine_manual`, `datasheet`,
`drawing`, `io_mapping`, `sop`, `inspection_report`, `iso_certificate`, `near_miss`, `training_note`,
`knowledge_document` (machinery/general).

### 6.2 Parsers (`ingestion/parsers/registry.py`)

| Parser | Handles |
|--------|---------|
| `pdf` | PDF (layout via **docling** in prod, `fallback_pypdf` in dev; tables via pdfplumber) |
| `excel` | XLSX/XLS (openpyxl + pandas) |
| `word` | DOCX (python-docx) |
| `json` | JSON structured docs |
| `text` | TXT / Markdown |
| `image_ocr` | Images (pytesseract OCR) |

Plus a special **`vision_diagram`** path (`parsers/vision_diagram.py`) for `drawing` documents: wiring/
schematic PDF pages with high vector-drawing density are sent to a **vision LLM** (`qwen3-vl:4b` via the
`vision_extract` profile) that reverse-engineers each page into Thai markdown (device/connection tables,
ASCII diagrams) plus a document-level device→pages+adjacency index and a system overview for cross-page
questions. This is the **active feature on the current branch** (`feat/vision-diagram-detailed-extract`).
Concurrency is capped (`ingest_vision_max_concurrency=4`; drawing.yaml may set `1`), streaming is
mandatory (Cloudflare 524 at ~100 s), and `max_tokens`/`num_ctx` are raised so long answers don't truncate.

### 6.3 Pipeline stages

```
upload → parse (streaming, row-by-row) → trust scan → transform/chunk → index → finalize
```

- **Trust / PII scan** (`ingestion/trust/`) — Presidio-based PII detection, secret detection, prompt-
  injection detection against exemplars. A document can be **quarantined** (`ingest_status=quarantined`)
  and require admin **release** (`POST /documents/{id}/release`) before it is indexed
  (`run_index_from_artifact` replays the stored parse artifact).
- **Chunking** (`ingestion/chunk/`, `chunking/`) — parent/child, semantic-heading, SOP-procedure,
  table-row, page-boundary strategies selected per document type / chunking profile.
- **Indexing** (`ingestion/index/`) — dense + sparse encode (`sparse/` supports bge-m3 sparse / SPLADE
  v3 / none), Postgres writer (metadata + lexical), Qdrant writer (vectors). Encoding uses a dedicated
  thread pool (`ingest_encode_workers`).
- **Generation swap (blue-green)** (`ingestion/ingest_swap.py`, `saga.py`) — a re-ingest writes to a
  *staging* generation, then atomically swaps and schedules purge of the old generation. This makes
  re-ingest safe and reversible (`rollback_generation_pin.py`). Failures abort staging cleanly.
- **OCR** — scanned/low-text PDF pages dispatch to the `ocr_heavy` Celery queue; if no worker is
  consuming, `ingest_ocr_inline_fallback=true` runs OCR inline instead of blocking.

### 6.4 Reliability

- Idempotency keys, per-doc locks (`IngestDocLock`), attempt counting, DLQ (`dlq_at`), transient vs.
  permanent error classification with retry, and a purge outbox. Stuck-pending jobs are rescued by a
  beat task every 5 min. Per-factory upload rate limits (Redis token bucket).
- Document hash uniqueness is **scoped per factory** (migration `0058`) so the same file can exist in
  two factories.

---

## 7. Data model

### 7.1 PostgreSQL (32 tables, 58 Alembic migrations)

Managed by SQLAlchemy 2.0 (async) + Alembic. Migrations auto-apply on API startup
(`RUN_MIGRATIONS_ON_STARTUP=true`, disable when a separate job owns migrations). Latest migration:
`0059_api_keys`.

| Group | Tables |
|-------|--------|
| **Org / tenancy** | `factories`, `factory_settings`, `machines`, `machine_aliases`, `components` + `component_aliases` (legacy, empty — component scope removed from the product; tables kept so no migration is needed) |
| **Identity / RBAC** | `users`, `roles`, `user_roles`, `job_positions`, `user_job_positions`, `user_factory_access`, `api_keys` |
| **Documents** | `documents`, `document_chunks`, `document_job_positions`, `document_access_log` |
| **Ingestion** | `ingestion_jobs`, `ingestion_events`, `ingestion_errors`, `ingest_purge_outbox` |
| **Chat** | `chat_sessions`, `chat_messages`, `chat_message_attachments` |
| **RAG / caching** | `verified_qa_cache`, `rag_scope_broadening_audit`, `audit_retrieval_log` |
| **Feedback** | `knowledge_feedback`, `knowledge_feedback_attachments` |
| **External analytics** | `external_data_sources`, `external_data_source_tables` |
| **Audit** | `audit_events_immutable` (WORM-style append-only audit) |

- `documents.ingest_status` lifecycle: `pending` → `running` → `completed` / `partial` / `failed` /
  `quarantined` → `pending_release` → `indexing` → `completed`.
- `chat_messages` carry `sources`, `confidence_tier`, `cache_hit`, and a `retrieval_snapshot` JSON that
  captures how the answer was produced (for audit and follow-up context).
- Session `context` stores **session slots** (machine lock, revision, pipeline stickiness, last chunk
  IDs) enabling multi-hop follow-up questions.

### 7.2 Qdrant (vector store)

- Base collections: `spark_docs` (machinery) and `spark_enterprise_docs` (HR/policy).
- **Sharding strategy** `qdrant_shard_strategy` = `single` | `per_factory` | `per_factory_category`;
  `qdrant_strategy.list_search_collections(factory_id)` resolves which collections to search.
- Vectors: dense `bge-m3` 1024-dim (cosine) + optional sparse. Payloads carry the **embedding lineage
  string** (e.g. `BAAI/bge-m3@sentence_transformers#1024`) so mixed-provider vectors are reconciled.
- Collection suffix versioning (`qdrant_collection_suffix_version`, e.g. `v2`) supports blue-green
  embed migration. `data/rag/` holds circuit flags.
- Nightly + 15-min **vector reconcile** beat tasks keep Postgres and Qdrant consistent (`auto_fix=True`).

### 7.3 Object storage

- `STORAGE_BACKEND=s3` in prod → **MinIO** on the box (`spark-documents` bucket). `local` backend writes
  under `data/` for dev. Original uploads, quarantine artifacts, machine/profile/feedback images, and
  chat attachments all go through the storage layer.

---

## 8. API surface

FastAPI, all under `/api/v1` (~101 routes across 22 routers). Interactive docs at `/docs` (Swagger) and
`/redoc`. Health/ops endpoints at root: `/` , `/healthz`, `/readyz` (`?lite`/`?deep`), `/metrics`
(Prometheus).

| Router | Representative endpoints | Purpose |
|--------|--------------------------|---------|
| `auth` | `POST /auth/login`, `/refresh`, `/change-password`, `/google/login`, `/google/callback`, `/oauth/exchange`, `/privacy-acceptance` | Auth, JWT issuance/refresh, Google OAuth, privacy acceptance |
| `chat` | `POST /chat/sessions`, `POST /chat/sessions/{id}/ask` (+ SSE stream), `GET /chat/sessions`, `/sessions/{id}/messages` | Chat sessions, ask (sync + streaming) |
| `ingest` | `POST /ingest/file`, `GET /ingest/{job_id}`, `/{job_id}/stream`, `/{job_id}/retry`, `/{job_id}/errors` | Upload & monitor ingest jobs |
| `ingest_preflight` | `POST /ingest/preflight` | Validate a file before upload |
| `documents` | `GET /documents`, `/{id}`, `/{id}/file`, `PATCH /{id}/visibility`, `/{id}/policy-findings` | Document library |
| `document_release` | `POST /documents/{id}/release` | Release a quarantined document |
| `machines` | `GET/POST/PATCH/DELETE /machines/*`, `/{id}/image`, `/{id}/aliases` | Machine CRUD |
| `admin` | users, job positions, factory settings, feedback review | Admin console backend |
| `admin_data_sources` | `POST/PATCH/DELETE /admin/data-sources/*`, `/{id}/test`, `/discover`, `/tables` | External Postgres Text-to-SQL config |
| `api_keys` | `POST /api-keys`, `/{id}/revoke` | Public API keys |
| `job_positions` | `GET/POST/PATCH /job-positions/*` | Job-position management + document ACL |
| `feedback` | `POST /feedback`, `GET/PATCH /{id}`, attachments | Knowledge feedback |
| `factories` | `GET /factories`, `POST /factories`, `DELETE /factories/{id}` | Factory management |
| `jobs` | ingest job listing/detail/stream | Job dashboards |
| `rag` / `rag_preflight` | `POST /rag/query`, `/rag/preflight` | Direct RAG (non-chat) |
| `streams` | SSE stream ticket mint + alert streams | Streaming governance |
| `system_admin` | `/dashboard`, `/actions/reset-rag-circuit`, `/actions/qdrant-sync`, `/actions/maintenance` | NOC dashboard + ops actions |
| `audit_export` | `GET /audit/export` | HMAC-signed audit export |

---

## 9. Authentication, authorization & trust

### 9.1 AuthN

- **JWT** (HS256, `JWT_SECRET`) issued by `POST /auth/login`, refreshed by `/auth/refresh`. The Next.js
  middleware verifies the same JWT (`JWT_SECRET` must match between API and web). Token version cache
  invalidates sessions on role/password change (`auth_token_version_cache_ttl`).
- **Google OAuth** ("Sign in with Google") — configured in prod (`GOOGLE_CLIENT_ID`, allowed domains
  `kcalsion.com, gmail.com`, default role `viewer`, default factory `E-03`). Public web callback flow at
  `/api/v1/auth/google/callback` + `/oauth/exchange`.
- **API keys** (`api_keys` table, migration `0059`) for programmatic/public API access; argon2-hashed.
- **Stream tickets** — short-lived signed tickets mint SSE connections (`mintStreamTicket`), required on
  Jetson prod (`require_ticket_for_sse`), with per-user/channel connection governance (429 before stream
  work).
- **Demo mode:** `AUTH_REQUIRED=false` runs unauthenticated requests as admin — **never expose on the
  internet** (the app logs a loud warning). Production forces `effective_auth_required=true` regardless.

### 9.2 AuthZ (`core/security.py`)

- **Principal** carries `roles` and per-factory access. Roles observed: `admin`, `super_admin`,
  `operator`, `release_documents`, `viewer`/`employee`.
- Helpers: `require_role`, `require_super_admin`, `can_access_factory`, `can_write_factory`
  (admin/operator), `can_release_documents`, `enforce_rag_filter_access`, `enforce_machine_access`.
- **Document ACL:** a user sees documents allowed by their **job positions**
  (`allowed_doc_ids_for_principal`). RAG retrieval is filtered by allowed doc IDs
  (`rag_acl_filter_mode = doc_id_set | payload_acl`) with a short-TTL ACL cache.

### 9.3 Trust, safety & compliance

- **Query policy / blocklist** (`configs/security/query_blocklist.yaml`) blocks disallowed queries.
- **Ingest content policy** (`configs/ingest_content_policy.yaml`, `configs/trust/`) — PII/secret/
  injection scanning with quarantine + admin release.
- **Compliance taxonomy** (`configs/compliance/`) — data classification + PII allowlist, validated at
  startup and by `scripts/validate_compliance_taxonomy.py`.
- **Production locks** (`configs/production_lock_v2.yaml`, `_v3.yaml`, `configs/eval/production_lock_v*.json`)
  — a signed/validated set of golden thresholds enforced at startup (`core/production_lock.py`) and in
  CI, so retrieval/ingest quality can't silently regress. HMAC-signed audit export
  (`AUDIT_EXPORT_HMAC_SECRET`).

---

## 10. Frontend (Next.js)

- **Stack:** Next.js 14 (app router), React 18, TypeScript, Tailwind, **Zustand** (state),
  **@tanstack/react-query** (server state), `react-pdf` (document viewer), `nuqs` (URL state). Version
  0.5.0, matching the API.
- **Structure:** `web/app/` routes; `web/components/` grouped by feature (chat, documents, ingest,
  admin, machines, dashboard, system-admin, trust, insights, workspace, ...); `web/lib/` holds API
  clients, `chatStream.ts` (SSE consumption), auth/JWT, i18n (Thai/English), offline sync, speech
  scaffolding, and trust presentation. **Note:** the frontend has speech/mic scaffolding
  (`web/lib/speech/`), but the backend `POST /chat/transcribe` endpoint mentioned in the CHANGELOG is
  **not present in the current code** — speech-to-text is not wired end-to-end today.
- **Chat UX** is deliberately Claude-like (recent work): live chain-of-thought "thinking" timeline with
  stage icons (searching/reading/generating), provisional-then-verified token streaming, citation
  drawer, confidence tiers, and error boundaries with remount-retry. Offline resilience: outbox
  coordinator, api-probe status banner, failed-queue panel.
- **API connectivity:** `NEXT_PUBLIC_SPARK_API_URL` (prod `http://spark-api.lan`); Mac thin-client and
  SSH-tunnel dev modes use `SPARK_API_PROXY_TARGET` Next.js rewrites for CORS-free access.
- **Tests:** lightweight `tsx` unit tests (`npm test`) + Playwright e2e (`npm run test:e2e`).
- **Deployment:** built with `scripts/build_web.sh` / `next build`; on Jetson runs as a systemd service
  (`deploy/jetson/spark-web.service`, installed via `scripts/jetson/install_web_service.sh`).

---

## 11. Background workers & scheduled jobs

Celery app: `src/spark/workers/celery_app.py` (broker + backend = Redis).

- **Queues:** `celery` (default — ingest pipeline) and `ocr_heavy` (OCR of scanned PDFs, routed via
  `task_routes`). Start with `celery -A spark.workers.celery_app worker` (see
  `scripts/start_celery_worker.sh`); on Jetson/dev the `ocr_heavy` queue must also be consumed.
- **Worker specifics:** each task runs its own `asyncio.run()` loop, so the DB uses NullPool and the
  Qdrant async client is reset after every task (both to avoid "event loop is closed" across tasks). This
  is why `SPARK_CELERY_WORKER=1` is set before importing `core.database`.
- **Beat schedule:**
  | Task | Interval | Purpose |
  |------|----------|---------|
  | `reconcile_vectors_task` | 24 h | Nightly Postgres↔Qdrant reconcile (auto-fix) |
  | `reconcile_all_factories_task` | 15 min | Frequent per-factory vector reconcile |
  | `cleanup_ingest_temp_task` | 6 h | Purge stale ingest temp files |
  | `dispatch_pending_purges` | 5 min | Drain the ingest purge outbox (old generations) |
  | `rescue_stuck_pending_task` | 5 min | Rescue jobs stuck in `pending` |
  | `policy_rescan_task` | 7 d | Weekly re-scan of documents against current trust policy |

---

## 12. Deployment & operations

> **Decision from handover:** the receiving team keeps the current setup — Jetson + external gateways.
> The self-hosted on-prem kit (`deploy/`) is documented as an alternative in §12.4.

### 12.1 Current production topology

- **Host:** NVIDIA **Jetson AGX Orin** (JetPack 5.1 / CUDA 11.4, aarch64). Data dir `data/` is root-owned.
- **Public URL:** `https://neospark.kcalsion.com` (fronted by a **Cloudflare tunnel** — note the 100 s
  Cloudflare edge timeout, which is why streaming is mandatory and vision extraction streams).
- **Services on the box:** Postgres (`:5433`), Redis (`:6380`), Qdrant (`:6333`/`:6334`), MinIO
  (`:9000`/`:9001`), FastAPI API (`:8000`), Celery worker(s), Next.js web (`:3000`, systemd), GPU sidecar
  (`:8137`, systemd). LLM/embed/rerank are **remote gateways** (KKU / kcalsion / ForgeNode).
- **Ollama note:** despite `ollama_*` settings, **there is no local Ollama listening on `:11434` on this
  box** — every LLM call goes through the remote gateways. Profiles that point at `localhost:11434`
  (`demo`, `translate_th`, `rag_th`) are dev-only and will fail here.

### 12.2 Base infra (`docker-compose.yml`)

Brings up Postgres 16, Redis 7, Qdrant v1.11.3, MinIO (+ `minio_init` bucket creation), and a daily
`pg-backup` (prodrigestivill/postgres-backup-local; keeps 7 daily / 4 weekly / 3 monthly). Compose
overlays:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base infra (Postgres, Redis, Qdrant, MinIO, pg-backup) |
| `docker-compose.dev-app.yml` | App + worker for dev, wires `GPU_SIDECAR_URL` |
| `docker-compose.prod.yml` | Production app overlay |
| `docker-compose.kcalsion.yml` | kcalsion gateway wiring (`host.docker.internal` → on-box proxy `:9090`) |
| `docker-compose.observability.yml` | Prometheus, Grafana, Jaeger |
| `docker-compose.gpu.yml` | GPU compose bits |
| `docker-compose.factory.yml` | Factory pilot profile |
| `docker-compose.mcp.yml`, `docker-compose.dev-hot.yml` | MCP / hot-reload dev |

### 12.3 Observability

- **Prometheus** scrapes `/metrics` (`ops/prometheus.yml`, `PROMETHEUS_URL`). **Grafana** dashboards in
  `ops/grafana/` (default admin/admin — change it). **Jaeger** for OTel traces (`otel` extra;
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317`). OTel is stub-safe when disabled.
- Key custom metrics: `spark_sse_connections_active/_rejected_total`, `spark_acl_cache_miss_duration_seconds`,
  `ingest_rows_total`, RAG latency/timeout counters. The `/system-admin` NOC dashboard surfaces 5xx KPIs,
  traffic, latency p95, and ingest donuts.
- **Cloudflared** config under `ops/cloudflared/`.

### 12.4 Alternative: fully self-hosted on-prem kit (`deploy/`)

For a LAN-only deployment with **no cloud/gateway dependency** (local LLM via Ollama/vLLM):

- `deploy/README-ONPREM.md` + `deploy/setup_onprem.sh --seed --pull-models` — one-click deploy
  (generates secrets, builds, starts, seeds admin). `deploy/docker-compose.onprem.yml` adds `ollama`,
  `web`, `api`, `celery_worker`, `celery_beat`, and an nginx reverse proxy (`deploy/nginx/`) with SSE
  support at `http://spark.lan`.
- Server sizing: min 16 GB RAM / 4 cores; recommended 32 GB / 8 cores for the 7B LLM + reranker.
- First login `admin / changeme` (with `--seed`) — change immediately.
- Jetson-specific compute scripts: `scripts/jetson/*` (bootstrap, install PyTorch CUDA, start/stop
  compute, Mac→Jetson migration), `deploy/jetson/README.md`.

### 12.5 Backups & data safety

- Postgres: daily `pg-backup` container (retention as above) → `pg_backups` volume; `BACKUP_ROOT` on the
  Jetson `.env` points at `/var/backups/spark`.
- Qdrant/MinIO: Docker volumes (`qdrant_data`, `minio_data`). **Ensure these volumes are in the backup
  plan** — losing Qdrant means a full re-ingest; losing MinIO means original documents are gone.
- Re-ingest tooling if vectors are lost/rebuilt: `scripts/full_reingest.py`,
  `scripts/full_reingest_v2_sparse.py`, `scripts/reconcile_ingest_vectors.py`,
  `scripts/qdrant_recreate_collections.py`, `scripts/ensure_qdrant_indexes.py`.

---

## 13. Local development setup

**Prerequisites:** Python 3.11–3.13 (not 3.14 — see pyproject note), Node 18+, Docker, and `uv` (the repo
is uv-managed; `uv.lock` is committed).

```bash
# 1. Start infra
docker compose up -d                       # Postgres, Redis, Qdrant, MinIO

# 2. Python env + deps
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                     # or: uv sync
alembic upgrade head                        # (also auto-runs on API startup)
python scripts/init_db.py                   # seed base data

# 3. Run the API (dev demo profile)
LLM_PROFILE=demo uvicorn spark.main:app --reload --port 8000 --app-dir src

# 4. Run a worker (separate terminal)
celery -A spark.workers.celery_app worker --concurrency=1 --loglevel=info -Q celery,ocr_heavy

# 5. Web UI (separate terminal)
cd web && npm install && npm run dev         # http://localhost:3000
```

- API docs: `http://localhost:8000/docs` · Web: `http://localhost:3000`.
- Convenience launchers: `scripts/dev.sh`, `scripts/start_local_infra.sh`, `scripts/mac_dev_thin.sh`
  (Mac thin client → Jetson), `scripts/jetson/ssh_tunnel_mac.sh`.
- For real answers in dev without a local GPU, point at the remote gateway: `LLM_PROFILE=gemma_remote`
  (or `kku_gemini`) with the appropriate key in a local `.env` (see §15). `demo` needs a local Ollama.
- **Optional extras** (`pyproject.toml`): `[compliance]` (Presidio), `[otel]`, `[ocr]` (opencv),
  `[speech]` (faster-whisper), `[smoke]`, `[factory]`.

---

## 14. Testing & quality gates

- **Python tests:** `pytest` (asyncio auto mode). Use `scripts/test.sh` on the Jetson — it sets
  `APP_ENV`/`SPARK_PROFILE=test`, NVMe caches, and the aarch64 `libgomp` preload, and points Redis at
  `:6380`. Chaos tests are marked `chaos` and excluded from default CI.
  - ⚠️ Running tests against the **production DB pollutes it** (creates artifacts that can trigger false
    system-admin alerts). Use the test profile / a clean DB. There are documented clean-slate reset steps
    in the team's internal notes.
- **Web tests:** `npm test` (tsx unit tests for offline LRU, speech transcript, JWT, ingest-upload,
  chat store) + `npm run test:e2e` (Playwright).
- **Eval harness:** `configs/eval/` holds golden real-doc suites, adversarial/red-team (injection,
  poisoning), safety-critical, and lexical-baseline suites. Gates: `scripts/ci_eval_gate.sh`,
  `scripts/release_gate.sh`, `scripts/nightly-eval*.sh`, `scripts/validate_production_lock_v3.py`,
  `scripts/validate_baseline_lock.py`. The **production lock** (§9.3) is the guardrail that prevents
  silent retrieval/ingest quality regressions.
- **Config contract checks:** `scripts/validate_ingest_configs.py`, `scripts/verify_config_contract.py`,
  `scripts/validate_config_docs.py`, `scripts/sync_retrieval_configs.py`.
- **CI note:** automated GitHub Actions (push/PR/schedule) and Dependabot auto-runs were **disabled** for
  a solo-dev workflow (manual `workflow_dispatch` only) to save Actions minutes. The receiving team may
  want to re-enable CI. Dependabot PRs still exist on `origin` (npm + pip) awaiting review.

---

## 15. Credentials & secrets inventory

**None of these secret *values* are in this document or committed to git.** `.env`, `kku_key.txt`,
`.env.kcalsion.*`, and `web/.env.local` are all gitignored. This table tells the receiving team **what
exists, where it lives, and what to rotate**.

| Secret | Where it lives | Used for | Action on handover |
|--------|----------------|----------|--------------------|
| **GitHub PAT** (`ghp_…`) | *was* embedded in the git remote URL in this box's `.git/config` — **scrubbed 2026-07-17** (remote is now a token-less HTTPS URL) | git push/pull | **🔴 Revoke the old token on GitHub** — it existed in plaintext on this machine, so treat it as exposed even though the remote URL is now clean. |
| `KKU_API_KEY` | `.env` / `kku_key.txt` | KKU gateway chat (`deepseek-v4-flash`) | Rotate; watch the daily token quota |
| `OLLAMA_API_KEY` | `.env` | kcalsion gateway chat (`api.kcalsion.com`) | Rotate |
| `OLLAMA_EMBED_API_KEY` | `.env` | kcalsion `/v1/embeddings` (if used) | Rotate |
| `FORGE_API_KEY` / `FORGE_EMBED_API_KEY` / `FORGE_RERANK_API_KEY` | `.env` | ForgeNode chat/embed/rerank | Rotate |
| `JWT_SECRET` | `.env` **and** `web/.env.local` | Sign/verify session JWTs (must match API↔web) | Rotate together; rotating invalidates all sessions |
| `POSTGRES_PASSWORD`, `POSTGRES_SQL_READONLY_PASSWORD` | `.env` | DB access | Rotate; update compose/app together |
| `DATA_SOURCE_ENCRYPTION_KEY` | `.env` (falls back to `JWT_SECRET`) | Encrypts stored external-DB passwords | Rotate carefully — re-encrypts external data-source creds |
| `GOOGLE_CLIENT_SECRET` | `.env` | Google OAuth | Rotate in Google Cloud console; update callback URL if domain changes |
| `S3_SECRET_KEY` / `MINIO_ROOT_PASSWORD` | `.env` | MinIO object storage | Rotate |
| `AUDIT_EXPORT_HMAC_SECRET` | `.env` | Signed audit exports | Rotate |
| `LANGCHAIN_API_KEY`, `DEEPANALYZE_API_KEY` | `.env` | Optional LangSmith tracing / DeepAnalyze | Rotate if used |

**Recommended handover procedure:** (1) revoke the GitHub PAT and reconfigure the remote; (2) rotate all
gateway keys with the gateway owners (kcalsion / KKU) and confirm the new team's quota; (3) generate a
fresh `JWT_SECRET` in both API and web env; (4) rotate DB/MinIO/OAuth secrets; (5) verify `/readyz` and a
end-to-end chat answer after rotation.

---

## 16. Known limitations, risks & roadmap

**Risks / things to watch (grounded in code comments, CHANGELOG, and the team's QA notes):**

1. **External-gateway dependency.** Chat quality and availability depend on the KKU/kcalsion/ForgeNode
   gateways. KKU enforces a **daily token quota** (~350k/day) and gateways have had Cloudflare 5xx
   outages. A gateway outage surfaces as `UNAVAILABLE_ANSWER`. Mitigation already in code: resilient
   embed ladder, rerank fail-fast to sidecar, circuit breaker. **Consider a local vLLM/`prod` profile as
   a fallback** if gateway availability becomes a problem.
2. **RAG concurrency under a shared remote LLM.** Because the LLM backend is shared and slow-ish, many
   concurrent questions can all hit the request budget and time out. `rag_inflight_max_global` exists to
   convert that into a fast retryable 429 but defaults to `0` (disabled). **Evaluate setting a global cap
   for the shared gateway.**
3. **Cloudflare 100 s edge timeout.** Long operations must stream. Vision diagram extraction and chat
   both stream for this reason; keep this constraint in mind for any new long endpoint.
4. **No local Ollama on the Jetson.** Dev profiles pointing at `localhost:11434` won't work on the box.
5. **QA readiness.** The team's internal QA review rated overall readiness ~62/100 at one point, flagging
   a cross-factory dedup issue, RAG concurrency collapse, limited OCR, and chunk-dump fallback behavior.
   Treat these as areas to validate against the current code before scaling to more factories.
6. **Test-pollution-in-prod-DB.** Running the test suite against the production database creates
   artifacts that can raise false alerts. Enforce test-profile isolation.
7. **Embedding lock-in.** Any change of embedding model/dim forces a full re-ingest. Plan migrations via
   the collection-suffix blue-green path (`scripts/migrate_embedding_collection.py`).

**Roadmap signals (features present but experimental / partial):**

- **Agentic routing** (parallel-tool agent) is behind a canary flag with a safety override; `routing_mode`
  defaults to `rag`. Shadow-comparison logging (`routing_shadow.py`) is largely a stub.
- **External Text-to-SQL** analytics is functional (admin-registered Postgres data sources) including
  compound SQL+document answers.
- **Vision diagram reverse-engineering** (current branch) is the newest ingest capability and still being
  tuned (prompt, concurrency, token limits).
- **Speech-to-text** (Whisper) — frontend mic scaffolding only; the backend transcribe endpoint is not
  in the current code (see §10), so this is not functional end-to-end.
- **Predictive** integration is `heuristic` backend only (`PREDICTIVE_BACKEND=heuristic`).

---

## 17. Operational runbook & troubleshooting

| Symptom | Likely cause | First checks / fix |
|---------|-------------|--------------------|
| Chat returns `ระบบ AI ไม่พร้อมชั่วคราว` (UNAVAILABLE) | LLM gateway down or KKU token quota hit | Check gateway health (curl the profile's `base_url` `/v1/chat/completions`); check KKU quota; check `/readyz?deep`. Consider switching `LLM_PROFILE` to `gemma_remote`. |
| Chat returns `ไม่พบข้อมูลในระบบ` (NO_DATA) unexpectedly | Evidence gate / rerank gate failing, or embed mismatch | Check the message's `retrieval_snapshot`; verify Qdrant collection has vectors for the factory; confirm embedding lineage matches; check circuit-breaker flag `data/rag/circuit_open.flag`. |
| RAG circuit open | Rolling error thresholds tripped | `POST /api/v1/system-admin/actions/reset-rag-circuit`; investigate the underlying LLM/embed errors. |
| Rerank slow / timing out | GPU sidecar or ForgeNode down | `curl http://localhost:8137/healthz`; `systemctl status spark-gpu-sidecar`; rerank falls back to fusion scores automatically. |
| Ingest job stuck in `pending` | No worker consuming, or lock held | Check Celery worker is up and consuming `celery` + `ocr_heavy`; the `rescue-stuck-pending` beat task runs every 5 min. |
| Ingest job `quarantined` | Trust/PII scan flagged the document | Review `GET /documents/{id}/policy-findings`; admin releases via `POST /documents/{id}/release`. |
| OCR never runs | No `ocr_heavy` worker | Ensure the worker consumes `ocr_heavy`, or rely on `INGEST_OCR_INLINE_FALLBACK=true`. |
| Qdrant/Postgres count drift | Missed writes | The 15-min reconcile fixes it; force via `POST /system-admin/actions/qdrant-sync` or `scripts/reconcile_ingest_vectors.py`. |
| `/readyz` 503 | A critical dependency is down | `readyz_full` reports which one (Postgres/Redis/Qdrant/LLM); `?lite` skips slow probes. |
| Web login fails after deploy | `JWT_SECRET` mismatch API↔web | Ensure the same `JWT_SECRET` in API `.env` and `web/.env.local`. |
| Vision extraction truncated | `max_tokens`/`num_ctx` too low, or Cloudflare 524 | Confirm `vision_extract` profile token limits and that extraction streams; check `ingest_vision_max_concurrency`. |

**Useful commands**

```bash
curl http://localhost:8000/readyz?deep         # dependency readiness (bypasses cache)
curl http://localhost:8000/metrics             # Prometheus metrics
python scripts/wait_ingest_idle.py             # wait for ingest queue to drain
python scripts/cleanup_broken_doc.py --help    # remove a broken document + its vectors
bash scripts/go_live_preflight.sh              # pre-go-live checks
```

---

## 18. Handover acceptance checklist

Functional (end-to-end):

- [ ] API starts; `/readyz?deep` passes (Postgres, Redis, Qdrant, LLM gateway all green).
- [ ] Web UI starts; password login **and** Google login work.
- [ ] A user can upload a document; the ingest job reaches `completed` (watch the live stream).
- [ ] The document appears in `/documents`.
- [ ] Chat answers a question from the uploaded document **with citations**.
- [ ] A Thai question over an English manual returns a cited (translated) answer, not NO_DATA.
- [ ] A deliberately-unanswerable question returns NO_DATA (fail-closed), not a hallucination.
- [ ] Admin can manage users, job positions, and job-position document access.
- [ ] Feedback can be submitted and reviewed.
- [ ] A quarantined document can be released by an admin and then becomes searchable.

Operational:

- [ ] All secrets rotated per §15 (GitHub PAT revoked first).
- [ ] Backups verified: Postgres dump restorable; Qdrant + MinIO volumes in the backup plan.
- [ ] GPU sidecar healthy (`:8137/healthz` → `device: cuda`) and enabled at boot.
- [ ] Celery worker + beat running and consuming `celery` + `ocr_heavy`.
- [ ] Grafana/Prometheus reachable; default Grafana password changed.
- [ ] KKU/kcalsion/ForgeNode gateway access confirmed for the new team (quota understood).
- [ ] `LLM_PROFILE`, `CORS_ORIGINS`, `WEB_APP_URL`, and OAuth callback match the new team's domain.

Knowledge transfer:

- [ ] Walkthrough of the three answer pipelines (§2.2) and the grounding gates (§5.4).
- [ ] Walkthrough of the ingestion staged pipeline + generation swap (§6).
- [ ] Ownership of the external gateways and their keys/quotas clarified with the gateway operators.

---

## 19. Glossary & further reading

**Glossary**

- **RAG** — Retrieval-Augmented Generation: retrieve documents, then generate a grounded answer.
- **RRF** — Reciprocal Rank Fusion: merges dense + lexical result lists.
- **CRAG** — Corrective RAG: verifies retrieved docs are actually relevant before/around generation.
- **NLI gate** — Natural-Language-Inference entailment check that the answer follows from the context.
- **bge-m3** — the multilingual dense embedding model (1024-dim) used everywhere; also provides sparse.
- **Generation swap** — blue-green re-ingest: write to a staging generation, atomically swap, purge old.
- **Scope judge** — the LLM step that classifies a question as chitchat / enterprise / machinery.
- **Session slots** — per-session state (machine lock, revision, pipeline stickiness) for follow-ups.
- **Production lock** — golden thresholds enforced at startup + CI to prevent quality regressions.
- **Fail closed** — when unsure, answer NO_DATA rather than guess.

**Existing repo docs** (useful but **may be stale — verify against code and this file**):

- `README.md` — quick start & product surface.
- `docs/architecture.md`, `docs/architecture/hybrid_retrieval_v2.md`, `docs/architecture/import_spine_v2.md`.
- `docs/operations-guide.md`, `docs/admin-guide.md`, `docs/user-guide.md`.
- `docs/api-overview.md`, `docs/public-api-integration.md`, `docs/internal/rag_payload_contract.md`.
- `docs/runbooks/` (audit export, ingest DLQ, cutover checklist), `docs/postmortem/template.md`.
- `deploy/README-ONPREM.md`, `deploy/jetson/README.md`, `gpu-sidecar/README.md`.
- `CHANGELOG.md` — the most reliable running record of what changed and why (large, well-maintained).

**Authoritative source-of-truth files** (when in doubt, read these):

- Config & profiles: `src/spark/core/config.py`, `configs/llm_profiles.yaml`, `.env.example`.
- Chat routing: `src/spark/services/chat_orchestrator.py`.
- Retrieval: `src/spark/retrieval/service.py`, `retrieval/kernel.py`, `retrieval/constants.py`.
- Generation: `src/spark/generation/pipeline.py`.
- Ingestion: `src/spark/ingestion/pipeline.py`, `ingestion/stages/runner.py`, `ingestion/parsers/registry.py`.
- Workers: `src/spark/workers/celery_app.py`.
- Auth: `src/spark/core/security.py`, `src/spark/api/v1/endpoints/auth.py`.

---

*Prepared as a code-grounded handover. Keep this file updated as the primary onboarding document; when it
diverges from the code, fix this file. Last verified: 2026-07-20 against branch `main` (see the header
above); see [`docs/DELIVERY_ACCEPTANCE.md`](./DELIVERY_ACCEPTANCE.md) for the delivery/acceptance record
built on top of this baseline.*
