# Changelog

All notable changes to Neo Chat are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [unreleased]

### Removed
- chore(repo): drop tracked `.cursor/` rules and `reports/` pilot manifests from the GitHub tree — local IDE/Cursor config and runtime eval/QA reports stay gitignored; move `pilot_soak_signoff.md` to `docs/runbooks/templates/`

### Changed
- chore(repo): CODEOWNERS sole maintainer `@fournarin` for delivery hand-off

### Added
- feat(deploy): expose Qdrant dashboard at `https://qdrant-neospark.kcalsion.com/dashboard` via Cloudflare Tunnel (`*.kcalsion.com` hostname; nested `qdrant.neospark…` fails Universal SSL)
- feat(api): public Swagger / ReDoc / OpenAPI — tunnel routes `/docs`, `/redoc`, `/openapi.json` to FastAPI (no login redirect); CSP relaxed on those paths so jsDelivr assets load; nginx allowlist removed for docs (metrics stay LAN-only); pin ReDoc JS to `redoc@2.1.5` because FastAPI's default `redoc@next` CDN URL 404s (blank page); tunnel paths are `/docs` + `/docs/*` (not `/docs*`) so `/documents` still reaches the web app

- docs: printable A4 Thai delivery forms in `docs/delivery-forms/` — client acceptance checklist (`NEOCHAT-CHECKLIST-2026-001`) and formal delivery/sign-off agreement (`NEOCHAT-ACCEPT-2026-001`) with retained rights for rebuild, concepts, portfolio, and know-how; companion to `docs/DELIVERY_ACCEPTANCE.md` and the Google Doc package.
- docs: `docs/DELIVERY_ACCEPTANCE.md` — English delivery & acceptance package for the v1.0.0 hand-off (scope tiers, AT-01–AT-05 acceptance tests, deemed acceptance/use, warranty and support windows, liability terms scoped to the employment-handover context, disclosed limitations/dead-code carve-outs, and a credential hand-off + sign-off form that records no secret values). Cross-linked from `docs/HANDOVER.md`, `docs/README.md`, and `README.md`.

### Changed
- docs: redesigned root `README.md` — colorful PNG banner hero, then a clean professional body (no mascots/emoji clutter); stack badges slimmed; content and links preserved.
- docs: polished `README.md` (tech-stack badges, tech-stack table, table of contents, accented architecture diagram, expanded documentation/community index) and gave the rest of the top-level `.md` set a consistent pass — `docs/README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`, `web/README.md`, `gpu-sidecar/README.md`, `deploy/README-ONPREM.md`, `.github/SUPPORT.md`.

### Fixed
- fix(deploy): Google OAuth login failed with `internal_error` after reboot because Docker DNS pointed at public resolvers (`8.8.8.8` / `1.1.1.1`) that this LAN blocks on port 53 — `api`/`celery_worker` now use the site LAN resolvers so token exchange can reach Google again
- docs: `GOVERNANCE.md` had four root-relative links pointing one directory too high (`../CHANGELOG.md`, `../CODE_OF_CONDUCT.md`, `../CONTRIBUTING.md`, `../configs/remediation/phase_gates_v3.yaml`) — all were broken since the file lives at the repo root.
- docs: `CONTRIBUTING.md` linked a nonexistent `docs/runbook.md`; repointed to `docs/operations-guide.md`.
- docs: `deploy/README-ONPREM.md` had a `REDIS_URL` table row stranded outside its table (orphaned by a paragraph inserted above it), rendering as a broken line instead of a table entry.
- docs: `web/README.md`'s route list was missing `/feedback`, `/machines`, `/admin/factories`, and `/system-admin`, which exist in the app.

## [1.0.0] — 2026-07-20

> First 1.0.0 release. Supersedes the 2026-07-18 decision to hold versioning at 0.x pending API stability (see the 0.9.0 note below) — declared stable at the project owner's direction.

### Changed
- Drawing/vision ingest: circuit-by-circuit reverse-engineering prompt (Thai markdown sections + device/connection tables), richer page UX headers, document-level device→pages+adjacency index and system-overview synthesis for cross-page questions (e.g. M18 impact / wire tracing); `vision_extract` max_tokens/num_ctx and drawing timeout raised for long answers
- Chat Q&A UX on `/chat` aligned closer to Claude: pondering star, prose-style thinking timeline, answer typography (~17px / 1.7), and user bubble spacing — sidebar and welcome unchanged

### Fixed
- fix(retrieval): rerank gate thresholds now follow the backend that actually scores — the GPU sidecar (bge) outranks Forge in `score_pairs`, but the gate loader picked the Forge-tuned (lower) thresholds whenever `FORGE_RERANK_ENABLED` was set, so live bge scores were gated too permissively; the bge-calibrated `min_rerank_score` floor likewise no longer overrides Forge-tuned gates when Forge really scores
- fix(system-admin): NOC dashboard reports measured values only — real SQLAlchemy pool metrics (in use / idle / overflow), honest "no data" service tiles when `/readyz` is unreachable, agentic circuit shown as OFF (stub, not a live breaker), cost KPI in THB (`USD_THB_RATE`, default 33) with fixed-rate disclosure, tooltip text visible again (portal CSS palette), debug console links work from remote browsers

### Removed
- Machine *component* concept (2026-07-18): the customer's data has no component hierarchy, so the `/api/v1/components` endpoints, `component_id` request/response fields (RAG filter, document metadata, agentic search), component alias resolution during ingest, and the remaining Component web-UI/type traces were removed. The empty `components`/`component_aliases` tables and the `component_id` columns/payload keys stay in place (all NULL) so no DB migration or re-index is required.
> Note (2026-07-18): this trim was partially reversed by later work in this same
> unreleased range — the system-admin NOC dashboard and the `/dashboard` and
> `/machines` routes are back in the current build (see Added below); agentic
> routing and Whisper transcribe remain removed.
- Text-to-SQL, external Postgres data sources, and admin data-source UI/API
- Agentic routing, shadow/canary comparison, IO mapping / wiring lookup tools, and DeepAnalyze integration
- Whisper speech-to-text (`POST /chat/transcribe`) and frontend microphone capture
- Factory ops surfaces: inventory, handover, repair analytics, machine/component CRUD, specialized document tables (drawings, certificates, inspections, incidents), system-admin NOC dashboard
- Demo/eval scripts and configs tied to maintenance, spare parts, shift handover, and factory pilot flows
- Structured ingest tables for repair history, purchase orders, IO mapping, and wiring I/O (RAG chunk index only)
- Frontend routes `/dashboard`, `/machines`, `/system-admin`, and dead admin factory panels; nav trimmed to chat, documents, upload, and admin

### Changed
- Home and primary workspace redirect to `/chat`; chat orchestrator is RAG-only (no agentic/SQL/structured fast paths)
- Document upload supports general knowledge types (PDF, Word, Excel, images, text, Markdown) without machine selector
- Docs (`README`, admin guide, architecture, operations) rewritten for document upload + Q&A scope
- Ingest postgres writer is a no-op for structured tables; trust scanner no longer loads machine specs

### Added
- Lightweight observability stubs so RAG pipeline tracing calls remain safe after observability module removal

- feat(rag): cross-lingual answers — Thai questions over English-only manuals serve cited extractive spans (translated when possible) instead of failing closed; evidence gate learns equipment-spec/safety vocabulary (enabling switch, HWTO/EDM, LED/system board); decomposition no longer splits frequency+procedure compound questions
- feat(rag): verified `citation_block` streaming — self-verify/NLI failures fall back to grounded extractive answers before `no_data`; final verified text replaces provisional tokens client-side; new `stream_phase` (searching/reading/generating) on SSE meta
- perf(rag): async GPU-sidecar rerank (no longer queues behind embed work on the default executor), in-flight busy-skip covers sidecar I/O, rerank timeout scales with candidate count, degraded rerank reuses fusion scores instead of loading the 2.2GB CPU cross-encoder; Qdrant search retries transient connection errors; LLM gateway calls retry transient network blips (max_retries=3)
- fix(config): `tagging`/`judge` LLM profiles pointed at a nonexistent local Ollama — routed to the remote gateway (broken session titling and every SQL-routed analytics answer)
- chore(ci): disable automated GitHub Actions (push/PR/schedule) and Dependabot — manual `workflow_dispatch` only; solo dev workflow to save Actions minutes

### Fixed
- fix(rag): streamed queries ran full retrieval twice per question (duplicate `_resolve_retrieval` call in `query_stream`)
- fix(core): `ProductionProfile.from_settings()` test branch dropped `require_gpu_rerank`/`ml_classifier_enabled` from `test_defaults()`, silently re-enabling the GPU-rerank startup gate in CI
- fix(storage): `LocalStorageBackend` no longer eagerly mkdirs all four storage roots at construction — directories are created lazily on first write, so an unwritable unused root can't break init
- fix(intent): Thai "เท่าไหร่" alone no longer forces SQL routing — spec-lookup questions (e.g. weight of a controller) stay on RAG unless a domain/temporal signal is present
- chore(tests): `scripts/test.sh` runner (APP_ENV, NVMe caches, aarch64 libgomp preload) + early torch/sklearn import in conftest to avoid static-TLS exhaustion on Jetson; stale tests updated to current contracts (multi-collection purge sweep, queued-job 5% progress, phase-meta ordering, staged-runner parser patching)

### Added
- feat(web): production SSE stream tickets — `mintStreamTicket` for chat ask + ingest job streams (`require_ticket_for_sse` on Jetson); reingest button on Documents; login/signup dark/light theme toggle; Jetson README sync guide and `JWT_SECRET` in Mac env examples
- feat(data-sources): external Postgres live query — admin registers connection + table allowlist at `/admin` (Postgres ภายนอก); chat routes analytic questions to `ExternalAnalyticsService` (migration `0054`, API `/api/v1/admin/data-sources`)
- feat(system-admin): NOC roadmap — incident strip, 5xx KPI + daily deltas, PostgreSQL/eval panels, TV fullscreen mode, mock default off; dashboard API `incidents` feed
- feat(system-admin): NOC control-room dashboard — Grafana dark TV layout, 6 chart panels (token split, users, messages, traffic, sessions, ingest), latency p95, ingest donut; timeseries API extended; fixes parallel DB session bug
- feat(jetson): Jetson AGX Orin compute kit — `deploy/jetson/` env template + README, `scripts/jetson/*` (bootstrap, PyTorch CUDA, start/stop, Mac→Jetson migration), `scripts/mac_dev_thin.sh`, `web/.env.mac-thin.example`, `SPARK_API_PROXY_TARGET` in Next.js rewrites for CORS-free Mac thin client
- feat(web): Gemini-style chat empty state (fog effect, logo welcome), Roboto/Noto Sans Thai fonts, root `/` redirects to login; Jetson SSH tunnel script + `web/.env.mac-tunnel.example`

### Fixed
- fix(dev): Mac local boot — auto-run Alembic on API startup (`RUN_MIGRATIONS_ON_STARTUP`), profile-aware non-fatal `/readyz` LLM probe (gateway WAF headers + Bearer), Celery `ocr_heavy` queue in `dev.sh`/`bootstrap_dev.sh`, `gemma_remote` sparse tokenizer via `BAAI/bge-m3`

### Added
- feat(app-layer-v2): Phase 3 SSE connection governance — enforced per-user/channel `ConnectionGovernor` (429 before stream work), `sse_policy` + `sse_frame`, alert stream fail-closed ACL for null `factory_id`, `remaining_connections` on stream ticket mint, metrics `spark_sse_connections_active` / `spark_sse_connections_rejected_total`
- feat(app-layer-v2): Phase 4 ACL correctness — `mutation_hooks` single entry for ACL-bumping writes, `factory_doc_index` for scoped compute, cache version race guard + `spark_acl_cache_miss_duration_seconds`, alert persist requires resolvable `factory_id`
- feat(app-layer-v2): Phase 13 legacy purge & pilot cutover — deleted `sliding_window.py` shim (rate limits via `rate_limit_lua.py`), `banned_patterns.sh` strict v2 in CI, extended import-boundary tests, `docs/api/streaming.md` v2 events (`token_provisional`, `error`, terminal contract), pilot smoke scenarios 9–11 (SSE admission, stale ticket, incomplete stream), README/deploy on-prem env table (`TRUSTED_PROXIES`, `AUDIT_EXPORT_HMAC_SECRET`)
- feat(app-layer-v2): Phase 10 error boundary resilience — `boundaryKey` remount retry on `PanelErrorBoundary`/`ChatErrorBoundary`, chunk-load detection in `AppErrorBoundary`, route coverage (workspace/repairs/system-admin/dashboard), `StreamErrorOverlay`, per-message `SparkMessageContent` fallback
- feat(app-layer-v2): Phase 9 offline network truth — ref-counted sync manager + outbox coordinator, `api-probe` with honest `ApiStatusBanner` retry, failed queue panel (`FailedQueuePanel`), multi-attachment offline blob store, GuestGuard slow-network timeout
- feat(app-layer-v2): Phase 8 operator trust gate — `requiresOperatorGate` composite logic, `OperatorTrustGate` on chat CTAs, `ProvisionalStreamBanner`, `StreamErrorChip` during send, scroll pin + jump chip, citation drawer focus trap
- feat(app-layer-v2): Phase 7 chat state rewrite — React Query as sole message store, `chatSessionStore` keyed by sessionId, `chatAbortRegistry` on session switch, O(1) `contentChunks` stream append, removed global `useChatStore`
- feat(app-layer-v2): Phase 6 unified frontend SSE fabric — `lib/streams/fabric.ts` completion contract (`StreamIncompleteError`/`StreamStallError`), `transportSseGet`/`transportSsePost`, deleted `askStream` and `stream-consumer.ts`, chat/alerts/ingest on fabric, provisional token UI in `StreamingBubble`
- feat(app-layer-v2): Phase 5 stream pipeline integrity — `token_provisional` / `citation_block` SSE phases, cooperative disconnect cancel, stream ask dedupe, honest agentic path (no pseudo-chunk tokens)
- feat(app-layer): Phase 0 constitution — `AppProfile`, unified API error envelope (`trace_id`, `code`, `retryable`), frontend `OperatorTrustState` trust contract, `app_layer_phase_gate.py`
- feat(app-layer): Phase 1 API platform — security headers, request ID, timeout, global IP rate limit, concurrency cap middleware; Redis sliding-window export rate limit; route policy registry for SSE/RAG timeouts — audit-response blueprint (`remediation_blueprint_v3/`), `phase_gates_v3.yaml`, `remediation_v3_phase_gate.py`, import spine v3 patterns, constitution contract tests; v2 README supersession banner; `production_lock_v2.yaml` v3 migration note
- feat(app-layer): Phase 2 auth hardening — fail-closed production auth, Redis login lockout, opaque single-use stream tickets (`POST /api/v1/streams/ticket`), removed JWT-in-query for SSE; frontend `mintStreamTicket` for chat and ingest streams
- feat(app-layer): Phase 3 SSE architecture — Redis pub/sub for alerts/ingest streams (poll loops removed), discrete DB session scopes for chat stream, `subscribe_channel()` event bus, client disconnect handling, dedicated `stream_engine` pool
- feat(app-layer): Phase 4 ACL and admin performance — Redis-backed document ACL cache with invalidation hooks, batched admin user/position queries, alerts list ack from row data, Redis chat ask dedupe
- feat(app-layer): Phase 5 streaming pipeline — live token streaming production default (`effective_spark_stream_live_tokens`), `RAGStreamPhaseMeta` pre-token SSE meta with degradation/retrieval_report, agentic canary chunked stream (no sync `ask()` fake token), structured `rag_at_capacity` 429, required trust fields on SSE `done`
- feat(app-layer): Phase 6 frontend transport — unified `transport` client with retry/circuit breaker, `networkStore` + `ApiStatusBanner`, auth split (`session`/`profile`), hook-based `WriteGuard`, `AuthGuard` on system-admin layout, React Query defaults, stream tickets via transport
- feat(app-layer): Phase 7 operator trust UX — `TrustSummaryRow`, confidence/citation/degradation banners, stream trust in `chatStore`, stop generation control, admin verify gating, SSE meta trust parsing
- feat(app-layer): Phase 8 realtime resilience — alerts SSE client (`subscribeAlerts`), ingest stream ticket reconnect, chat stream 30s stall watchdog (`StreamStallError`), stream ticket mint debounce, `ConnectionQualityChip` on workspace/chat shells
- feat(app-layer): Phase 9 offline industrial resilience — chat history IDB cache, ask outbox with reconnect drain (`sync-coordinator`), attachment blob queue (10MB cap), `FactoryLockBanner` + production factory selection gate, honest PWA manifest/settings, `QueuedAskBubble` + offline history banner, E2E `offline-chat-queue.spec.ts`
- feat(app-layer): Phase 10 frontend perf — virtualized `ChatHistory` (`@tanstack/react-virtual`), isolated `streamingMessage` store slice, `AppErrorBoundary`/`ChatErrorBoundary`/`PanelErrorBoundary`, modal focus trap, skip link + `main-content` landmarks, reduced-motion loading dots, Thai operator strings, E2E `chat-virtualization.spec.ts`
- feat(app-layer): Phase 11 edge deploy — Redis required at production startup (no silent `_MemCache` fallback), `/readyz` Redis + DB pool checks with HTTP 503, nginx metrics/docs IP allowlist + API rate limit zone, default `ONPREM_API_WORKERS=2`, `scripts/load/app_layer_smoke.py`
- feat(app-layer): Phase 12 contract gates — `tests/app_layer/contracts/` (error envelope, trust fields, SSE schema, frontend trust mapping), `security/test_auth_bypass.py`, import boundary tests, `production_lock` `app_layer` section + startup validation, CI job `app-layer-contracts`, nightly `nightly-app-load.yml`, `docs/architecture/app_layer_th.md`
- feat(app-layer): Phase 13 legacy teardown — `scripts/app_layer/banned_patterns.sh`, deleted `web/lib/chatStream.ts` shim, `docs/api/streaming.md`, `docs/runbooks/app_layer_pilot_smoke.md`, factory pilot runbook app-layer gates, pitch script alignment, post-pilot monitoring in `metrics_v3.md`
- feat(remediation-v3): Phase 1 document truth layer — layout parse adapter (`parse/layout/`), page-faithful parent-child via `page_aware_parent_child`, PDF block pipeline (no full-text concat), Word structured tables, JSON size guards, `spark_layout_parser` setting, production lock `layout_parser: docling`
- feat(remediation-v3): Phase 2 ingest saga & idempotency — `DocumentAccumulator` full-doc quarantine, streaming parse drain on trust hit, fail-closed staging abort, partial unique idempotency index (migration 0051), idempotency key cleared on terminal jobs, explicit partial swap (`swap_partial_explicit` + metric), purge exhausted → DLQ, 64-bit advisory locks
- feat(remediation-v3): Phase 3 trust & adversarial defense — severity-calibrated gate (low OCR no quarantine), `document_scan.py` full-doc scan before swap, ML classifier on batch/post-chunk paths, text normalization homoglyph fold, block→DLQ under permanent profile, `always_quarantine_categories`, invalid regex fails at policy load
- feat(remediation-v3): Phase 4 payload contract enforcement — `ParsedRecordPayload` / `QdrantPayloadSchema` (extra=forbid), denylist replaces YAML `payload_fields` whitelists, strategy-aware required fields, 100% safety payload key audit, `config_validator.py` startup gate
- feat(remediation-v3): Phase 5 embed & sparse compute pipeline — `IngestComputePool` dedicated thread pool, batched dense+sparse via `batch_encode.py`, embed retry with transient OOM/timeout classification, sparse symmetry contract, `sparse_encode_empty_total` metric; semantic embedding chunking gated behind `offline_only` (removed from ingest hot path)
- feat(remediation-v3): Phase 6 parse & chunk consolidation — true `SopProcedureChunker` (LOTO/warning/step blocks), `stable_id.py` UUID5 chunk lineage, canonical strategy registry (`parent_child` deprecated), `sop.yaml` → `sop_procedure`, table stable IDs
- feat(remediation-v3): Phase 13 eval gates & production lock — `production_lock_v3.yaml` + `production_lock_v3.json` sole threshold sources; `validate_production_lock_v3.py` strict outcome gate; HMAC-signed eval tokens (`eval_token.py`) bound to report hashes; held-out golden set (100+ cases); v1 eval locks removed; CI `production-lock-v3` job; `release_gate.sh` / `go_live_preflight.sh` / `evaluate_baseline.sh` rewritten for v3
- feat(remediation-v3): Phase 14 compliance taxonomy & WORM audit — taxonomy aligned to 15 ingestion types (`validate_compliance_taxonomy.py`); Presidio PII scan with factory allowlists (`presidio_scanner.py`, optional `[compliance]` extra); WORM events for `quarantine_release`, `circuit_reset`, `eval_token_issued`, `rag_scope_broadened`; audit export gated to `compliance_officer` with classification filter and rate limits
- feat(remediation-v3): Phase 16 go-live cutover — v3 factory pilot runbook, `go_live_preflight.sh --v3 --strict`, cutover report archival, generation-pin rollback helper, v3 contract tests; v2 checklist superseded banner
- feat(remediation-v3): Phase 15 adversarial soak & chaos — `configs/load/pilot_profile.yaml`, chaos test suite (`tests/chaos/`, `@pytest.mark.chaos`), load soak scripts, red-team eval expansion (≥50 cases), `nightly-chaos-v3.yml`, pilot soak sign-off template
- feat(remediation-v3): Phase 12 observability & metrics truth — semantic RAG intent/degraded labels, ingest DLQ/quarantine/SLO metrics, retrieval leg histograms, rerank gate fail counter, optional OTel tracing, confidence tier from answer_path/citations
- feat(remediation-v3): Phase 10 generation grounding overhaul — `GenerationPolicy` wired in sync/stream RAG paths, structured safety via `with_structured_output` (no regex JSON), validated pseudo-stream default (`spark_stream_live_tokens`), NLI lexical gate for safety, WORM audit on `numeric_grounding_fail`, `spark_extractive_first` env override
- feat(remediation-v3): Phase 8 circuit breaker isolation — per-factory/per-dependency bulkheads (`retrieval/circuit/`), `spark_rag_circuit_open` gauge, embed/rerank/llm/unhandled trip independently, factory-scoped Redis keys, WORM audit on manual reset
- feat(remediation-v3): Phase 7 retrieval degraded-path rewrite — deleted `calibrate_scores.py`, rank/raw fusion degraded gate (`degraded_fusion_floors.yaml`), `DegradedRetrievalPolicy`, safety fail-closed abstain/extractive-only on CE outage, degradation contract `rerank_degraded_policy` + `sparse_available`
- feat(remediation-v2): Phase 16 go-live cutover — v2 factory pilot runbook, `remediation_blueprint_v2/CUTOVER_CHECKLIST.md`, `go_live_preflight.sh`, postmortem template; v2 README all phases complete; v1 blueprint archive note
- feat(remediation-v2): Phase 15 eval gates & production lock — runtime `eval_gate` blocks ingest swap on breaking embed/sparse/policy changes without Redis eval token; `production_lock_v2.json` + `validate_production_lock_v2.py`; extended `remediation_v2_phase_gate.py` with `--eval`/`--threshold`; `issue_eval_token.py`, `online_feedback.py`; Grafana `rag_slo.json` v2 metrics, `ops/prometheus/alerts/rag_v2.yaml`; CI `production-lock-v2` job on develop PRs
- feat(remediation-v2): Phase 14 audit compliance & pre-flight — hash-chained WORM audit sink (`audit_events_immutable`), wired events for ingest swap, scope broadening, safety refusal, quarantine release, circuit reset; ingest preflight trust dry-run (`ingestion/preflight/validator.py`); `POST /rag/preflight`; `GET /api/v1/audit/export` compliance bundle; `configs/compliance/data_classification.yaml`; runbook `docs/runbooks/audit_export.md`
- feat(remediation-v2): Phase 13 shim teardown — deleted `services/rag/` compat tree; canonical modules under `spark.retrieval` and `spark.generation`; import spine CI (`test_import_spine_v2`, `test_no_services_rag_imports`); `docs/architecture/import_spine_v2.md`
- feat(remediation-v2): Phase 12 session/cache/rewrite safety — versioned QA cache fingerprint (embed lineage, generation hash, policy + intent weight versions), cache-hit revalidation gate (`qa_cache_validator`), session evidence TTL decay, rewrite guard verdict in retrieval snapshots, migration clearing stale cache rows
- feat(remediation-v2): Phase 11 generation streaming & grounding — real `llm.astream()` token events with post-stream citation validation, mandatory extractive-first for safety/procedure intents, structured safety schema (`SafetyAnswerSchema`, `constrained_safety.py`), `numeric_grounding_fail` answer path, web SSE sources metadata (`citations_verified`, `answer_path`)
- feat(remediation-v2): Phase 10 safety & admission — unified `rag_admission_guard`, stream `allow_scope_broadening` parity, YAML query blocklist (50+ patterns), rewrite guard for locked slots, `system_degraded` circuit-open UX, request deadline budget, scope-broadening audit table
- feat(remediation-v2): Phase 9 intent fusion optimization — YAML weight table (`intent_weights_v2.yaml`), `intent/apply.py` document_type filter/boost, calibration script + `retrieval_calibration.yaml`, LTR feature logging, `intent_weight_version` in retrieval snapshots
- feat(remediation-v2): Phase 8 retrieval engine hardening — mandatory `factory_id`, global multi-shard RRF (`shard_search.py`), structured Qdrant failure logging + `spark_rag_vector_collection_fail_total`, embed-error circuit wiring, `system_degradation` on RAG/chat API responses, removed `retrieval/core.py` shim
- feat(remediation-v2): Phase 7 trust & content SLOs — per-record trust scan, post-chunk boundary scan, secrets/PII rules, `quality/slo.py` finalize gates, `ingest_quality_slo_breach` notifications
- feat(remediation-v2): Phase 6 parse & chunk consolidation — canonical chunk registry, layout `ParsedBlock` pipeline, modality chunkers (SOP/table_row/repair_event), PDF table extract warnings in job events, `parser_version` payload lineage
- feat(remediation-v2): Phase 5 sparse & hybrid rewrite — BGE-M3 tokenizer sparse encoder, `sparse_encoder_id` payload lineage, single app fusion point (`retrieval/engine.py`), `docs/architecture/hybrid_retrieval_v2.md`, production lock `sparse_encoder: bge_m3`
- feat(remediation-v2): Phase 4 index saga — bidirectional swap verify, purge outbox + Celery retry, generation-scoped `repair_history`, safety doc partial swap block, `ingest_quality_slos.yaml`
- feat(remediation-v2): Phase 3 streaming ingest — batch orchestrator, resource budgets, async OCR polling, `POST /ingest/preflight`
- feat(remediation-v2): Phase 2 ingest concurrency — Postgres doc advisory lock, job idempotency key `(doc_id, file_hash, config_hash)`, generation-scoped dedup, Celery-only transient retry, `docs/runbooks/ingest_dlq.md`
- feat(remediation-v2): Phase 1 truth layer — runtime `EmbedProfile` lineage in Qdrant payloads, `resolve_hybrid_weights` for factory+intent fusion, metrics v2 (`spark_rag_query_total`, `spark_rag_scope_broadened_total`, `spark_rag_embed_error_total`), QA cache embed fingerprint, `verify_config_contract.py`
- feat(remediation-v2): Phase 0 constitution — `production_lock_v2.yaml`, `production_lock.py` startup validation, `degradation_contract.py`, import spine v2 stub, `remediation_v2_phase_gate.py`, kernel degradation hook
- feat(remediation): Phase 13 legacy teardown — removed RAGFlow settings and legacy synthesis path (`_synthesize_from_docs`, regex `_translate_manual_step`), `deprecated_config_usage_total` startup audit, `scripts/audit_dead_code.sh` in CI, migration guide `docs/migrations/v0.6-native-only.md`, landing/docs sync (bge-m3 1024-dim)
- feat(remediation): Phase 12 eval release gates — consolidated `configs/eval/` suite, adversarial blocking on every PR, `phase_gates.yaml`, `nightly-rag-full.yml`, and `--threshold` on `remediation_phase_gate.py`
- feat(remediation): Phase 13 cutover — `test_import_spine.py`, `docs/runbooks/factory_pilot_cutover.md`, `docs/architecture/rag_spine.md`, `wait_ingest_idle.py`, web degradation banner for `retrieval_report.degraded`, archived `remediation_plan/` → `docs/archive/remediation_plan_v1/`

### Removed
- **BREAKING:** demo factory fallback (`F-01`/`F-02`) in `list_search_collections` — production retrieval requires explicit `factory_id`
- **BREAKING:** duplicate chunk implementations (`chunking/strategy.py`, legacy `ParentChildChunker` V1, hash-bucket sparse) — use `spark.ingestion.chunk.registry` and `ParentChildChunker` in `chunk/parent_child.py`
- **BREAKING:** hash-bucket pseudo-BM25 sparse encoder (`hash_sparse_legacy`) — full Qdrant re-ingest required after Phase 5 deploy
- **BREAKING:** RAGFlow integration surface — `ragflow_*` settings, sidecar health checks, and legacy deterministic synthesis helpers; production ingest/RAG is native-only (`INGEST_BACKEND=native`)
- feat(remediation): Phase 11 vector consistency ops — scheduled PG↔Qdrant reconcile (`vector_reconcile_service`, Celery beat), drift alerting + `vector_drift_detected_total`, chunk lineage (`content_hash`, `embed_model`, `embed_model_version`), blue-green collection suffix + migration script/runbook, policy re-scan task, parent batch load index, ingest temp cleanup beat
- feat(remediation): Phase 10 multi-turn state — query rewrite (`query_rewrite`, `follow_up`), rules/LLM retrieval expansion, structured `revision_sort_key` + latest-revision filter fix (`v10` > `v2`), `retrieval_snapshot` on chat messages, replay API, and `confirmed_machine_id` session context
- feat(remediation): Phase 9 grounding hardening — extract-then-paraphrase pipeline (`extractive_pipeline`, `evidence_spans`, `numeric_grounding`, `translation`), unit-aware numeric validation, Thai fail-closed with dedicated `translate_th` profile, prompt deduplication, and streaming parity (no uncited tokens)
- feat(remediation): Phase 8 RAG safety — core `RAGService` circuit breaker (`data/rag/circuit_open.flag`), scope-safe fallback ladder v2 with `allow_scope_broadening`, Redis RAG rate limits, machine-conflict hardening, safety-critical fail-closed path, admin `reset-rag-circuit`, and Grafana SLO panels
- feat(remediation): Phase 7 hybrid fusion rerank — `fusion_v2` (RRF/weighted/convex), per-factory `rag.fusion_method` + weights, GPU batched `reranker_service`, session rerank score cache, intent-aware LOTO/SOP relevance gates, optional Qdrant sparse vectors (`SPARK_SPARSE_VECTORS_ENABLED`), and `scripts/benchmark_retrieval_latency.py`
- feat(remediation): Phase 6 lexical engine — `services/rag/lexical/` package (Postgres FTS v2 default, legacy + OpenSearch stub), stored `content_tsv` GIN index, query normalization with boosted part/alarm terms, `rag_lexical_degraded_total` metric; removed Qdrant scroll lexical recovery
- feat(remediation): Phase 5 RAGFlow decoupling — native-only ingest/retrieval spine; removed `integrations/ragflow`, RAGFlow compose/docs archived; deprecated `ragflow`/`auto` backends resolve to `native`
- feat(remediation): Phase 4 ingest quality — OCR confidence gates, contextual chunk headers for embedding, cross-page PDF chunking, Word parser parity (parent-child/tables), PG-only `parent_content`, and `structure_aware` chunking profile
- feat(remediation): Phase 3 ingest reliability — Celery autoretry/DLQ, row-level dedup, alias `on_fail: warn`, partial job notifications with skip breakdown, per-factory single-file rate limit, and `POST /ingest/jobs/{id}/retry`
- feat(remediation): Phase 2 ingest security — content policy scanner, document quarantine/release workflow, retrieval filters for quarantined corpus, and `release_documents` RBAC
- feat(remediation): Phase 1 config truth — `ResolvedIngestConfig` with chunking/embedding profile merge, factory-aware ingest backend resolver, `SPARK_SEED_SKIP_EMBED` fail-closed guard, and config validation CLIs
- feat(remediation): Phase 0 scaffolding — `RemediationFlags` (env + per-factory `features` overrides), ingest↔retrieval payload contract tests, structured RAG/ingest observability keys, `scripts/remediation_phase_gate.py`, and Grafana `rag_slo` dashboard stub

## [0.9.0] — 2026-06-20

> **Enterprise handover release** — on-prem deployment kit, Thai localization, super-admin ops, pre-flight security audit, repository spring-clean, and GitHub enterprise standards (CONTRIBUTING, SECURITY, CodeQL, Dependabot). Production-ready for factory LAN delivery.
>
> _Renumbered from 1.0.0 in the 2026-07-18 versioning cleanup (see `docs/archive/release-tags-2026-07-18.md`); the project stays in 0.x until the API is declared stable. Historical PR #235 (`release/v1.0.0-enterprise-handover`) refers to this release._

### Added
- deploy(on-prem): factory intranet deployment kit — `deploy/docker-compose.onprem.yml`, SSE-safe Nginx, `deploy/setup_onprem.sh`, `deploy/README-ONPREM.md`
- feat(iam): `users.is_super_admin` (migration `0035`); `/api/v1/system-admin/*` infrastructure dashboard and danger-zone actions
- feat(web): `/system-admin` God Mode dashboard with `SuperAdminGuard`
- feat(web): Phase 4 product polish — executive KPI row, `DashboardRepairSummaryBar`, `ObservabilityPanel`
- feat(web): Phase 4.5 Thai localization (hybrid UX) across chat, dashboard, admin, and shared UI states
- feat(ingest): table-aware PDF extraction, parent-child chunking (migration `0033`), generation-swap re-ingest
- feat(sql): read-only Postgres role + factory Row-Level Security for Text-to-SQL
- feat(eval): Tier 1 no-API baseline lock (`evaluation_baseline_lock_no_api.json`, 91.67%)
- docs: enterprise GitHub polish — `CONTRIBUTING.md`, `SECURITY.md`, `GOVERNANCE.md`, `LICENSE`, architecture README
- github: issue/PR templates, `CODEOWNERS`, Dependabot, CodeQL workflow
- docs: `docs/README.md`, `docs/internal/` index; repo spring-clean (`docs/internal/`, `.gitignore`)

### Removed
- chore(repo): TestSprite scratch, one-off `qa_prompt_b_gap.py`; expanded `.gitignore` for local artifacts

### Changed
- chore(release): pre-flight security audit — token revocation, SQL GUC bypass block, Redis leak fix, orphaned component cleanup
- refactor(web): chat stack decomposition — Zustand store, typed SSE, modular gemini components, `lib/api/` split, `QueryBoundary`
- refactor(rag): hard-wired hybrid retrieval → RRF → cross-encoder gate; machine-anchored fallback ladder
- perf(db): migration `0034_crud_performance_indexes`; configurable Postgres pool sizes
- perf(api): eliminate N+1 queries; non-blocking S3/streaming downloads
- docs: README badges, mermaid architecture diagram, collapsible reference sections
- chore(config): production LLM profiles use `qwen3.6:35b-a3b`; CI RAG baseline `--skip-requires-live-api`

### Fixed
- fix(web): chat SSE streaming infinite re-render — stable `useSessionStreamingMessage` / `useSessionStreamStatus` equality subscriptions, no-op session store patches, repair KPI null guards; Phase 12 E2E SSE specs green
- fix(rag): machine-scoped retrieval with factory-wide chunks; off-topic eval guard; SOP LOTO context ordering
- fix(web): E2E smoke Thai sidebar labels; `useEffect` cleanup in landing hero and service worker
- fix(ci): SQL RLS integration test seed guard; deterministic eval LLM mock

## [0.8.1] — 2026-06-19

> **Post-v0.8.0 polish** — Production Readiness ~92/100; feedback source linking, notification smoke test, factory defaults.

### Added
- feat(feedback): auto-link `doc_id`/page จาก chat message sources; clickable sources ใน quality-failures + feedback drawer
- feat(notifications): `inventory_report_ready` event เมื่อรายงานสต๊อกเสร็จ; `handover_validate.py --notify-test` + `kcalsion-go-live.sh --notify-test`
- chore(factory): `INGEST_BACKEND=auto` default ใน `docker-compose.factory.yml`

### Changed
- docs: checklist/roadmap sync v0.8.1 · ~92/100; kcalsion go-live ใช้ `main` + tag v0.8.x

## [0.8.0] — 2026-06-19

> **Enterprise Phase 5 closure** — per-factory predictive, Insights Phase 3, OCR pipeline, PDF reports, Whisper offline, RAGFlow go-live gates.

### Added
- feat(predictive): per-factory `predictive_backend` resolution via `FactoryConfigService`; admin UI + `docker-compose.factory.yml` default `hybrid`
- feat(insights): factory timezone wired into pulse/trends/heatmap; `X-Bucket-Tz` header + `GET /insights/bucket-meta`
- feat(insights): Phase 3 — `GET /insights/factory-benchmark`, `/correlation-hints`, `/ai-questions/drilldown/export` (CSV)
- feat(web): dashboard panels — factory benchmark (admin), correlation hints, CSV export, timezone labels
- feat(ocr): preprocess pipeline (contrast + optional deskew via `[ocr]` extra); low-confidence notifications; Documents filter "OCR ต่ำ"
- feat(inventory): `GET /inventory/reports/{id}/download.pdf` + UI PDF download (`[factory]` extra / reportlab)
- feat(chat): `POST /api/v1/chat/transcribe` (Whisper optional `[speech]`); capabilities `speech.whisper`; MediaRecorder fallback chain
- feat(ops): RAGFlow `readyz` gate in `handover_validate.py` + `kcalsion-go-live.sh --validate`
- test: `test_predictive_factory`, `test_insights_phase3`, `test_ocr_preprocess`, `test_inventory_report_pdf`, `test_whisper_api`; extended RAGFlow retrieve mock

### Changed
- chore(config): `OCR_CONFIDENCE_ALERT_MIN`, `WHISPER_*`, `insights_correlation_spike_ratio`; production startup warns when global `predictive_backend=heuristic`

### Added (carried from pre-release)
- feat(web): inventory executive report panel — generate native/DeepAnalyze report, poll status, download Markdown on `/inventory`
- feat(ops): RAGFlow parity gate in `handover_validate.py` when `INGEST_BACKEND=ragflow|auto`
- test: `test_ragflow_integration.py` mocked ingest adapter; `test_inventory_reports.py` API smoke

## [0.7.0] — 2026-06-19

> **Enterprise chat & ingest platform** — SSE chat, intent routing, RAG trust, factory config, ingest SSE/batch, notifications, eval gates, and admin factory tuning since v0.6.0.

### Added
- feat(hardening): wire `FactoryConfigService` RAG `top_k` / `min_max_score` into orchestrator + retrieval
- feat(hardening): `JobsTable` SSE live progress via `useIngestJobStream`; slower list poll while streaming
- feat(hardening): outbound notifications on `ingest_failed` + `insights_hotness`
- feat(hardening): `verified_at` on `chat_messages` + `GET /ingest/batch/{batch_id}`
- feat(hardening): cache lifecycle integration test; `--semantic` chunk gate; `--ragflow-parity` eval
- feat(cache): indexed `question_hash` + `filter_fingerprint`; persist `confidence_tier`/`cache_hit` on messages
- feat(chat): admin ปุ่ม "ยืนยันคำตอบ" + nightly LLM job เมื่อตั้ง `OLLAMA_BASE_URL`
- feat(ingest): `IngestProgressEmitter` + `GET /ingest/jobs/{id}/stream` SSE + `POST /ingest/batch`
- feat(ingest): `ChunkingStrategy` (recursive/semantic) + OCR confidence badge ใน Documents hub
- feat(factory): `FactoryConfigService` + per-factory RAG/ingest/notifications settings
- feat(notifications): `NotificationProvider` (webhook/SMTP/LINE) per factory
- feat(admin): `audit_retrieval_log` + CSV export
- feat(insights): factory timezone resolution via `FactoryConfigService`
- feat(chat): `QuestionRouting` — แยก `route` (rag/sql) กับ `is_followup`; แก้ followup+analytic conflict
- feat(chat): SSE answer streaming (`AskRequest.stream`) พร้อม ChatStreamProtocol
- feat(rag): `context_budget` token guard ก่อนส่ง LLM; Prometheus `spark_context_trim_total`
- feat(chat): multi-turn LLM history ผ่าน `MessagesPlaceholder` + sliding window
- feat(chat): query compression สำหรับข้อความ >500 ตัวอักษร; `question_max_length` 3,000
- feat(chat): `GET /api/v1/chat/capabilities` + Settings แสดง server model จริง
- feat(web): chat composer แสดงตัวนับ `x/3000` + CTA อัปโหลดเมื่อข้อความยาว
- feat(ops): `kcalsion-go-live.sh` รัน `evaluate_baseline.py` + chat_routing cases
- feat(eval): `mode: chat` + `chat_chain` ใน `evaluate_baseline.py`; 60+ YAML cases
- feat(chat): `ConfidenceSignals` + `confidence_tier` ใน API/SSE + `ConfidenceBadge` UI
- feat(chat): Stage B LLM router (`ROUTER_LLM_ENABLED`) สำหรับคำถามคลุมเครือ
- feat(rag): `TokenCounter` interface (tiktoken/ollama/char_ratio)
- feat(cache): `QACacheService` opt-in verified cache + ingest invalidation + admin verify API
- feat(insights): `GET /api/v1/insights/quality-failures` + dashboard panel
- feat(feedback): server-side Q/S/A context snapshot เมื่อมี `message_id`
- feat(ops): `scripts/nightly-eval.sh` + nightly workflow jobs (routing + deterministic)

### Changed
- fix(chat): analytics path ใช้ `effective_question`; SQL follow-up ได้บริบท
- chore(config): `.env.factory.example` ใช้ `LLM_PROFILE=gemma`; production ห้าม `demo` profile

### Added
- feat(demo): `seed_customer_demo.py` orchestrator — presentation profile (curated repairs, no duplicate data), `--reset --ingest --validate`
- feat(demo): `run_customer_demo.sh` for local and kcalsion; `demo_polish.py` for dashboard chat/feedback samples
- feat(demo): restored `demo_presentation_repairs.py`, `demo_scenarios.py`; `--skip-maintenance` / `--skip-operational` flags

### Changed
- chore(demo): `bootstrap_demo.sh` defaults to `presentation` profile; skips `repair_history` xlsx ingest
- chore(demo): `kcalsion-go-live.sh` uses `seed_customer_demo.py`; `demo_playbook.md` documents customer demo flow
- fix(chat): remove verified Q&A similar-question cache — every ask runs fresh RAG/analytics so updated documents are not shadowed by stale cached answers

### Fixed
- fix(web): global error recovery pages (`error.tsx`, `global-error.tsx`); Thai 404 with home/chat/dashboard links
- fix(api): paginated `GET /chat/{session_id}/messages` (cap 500 client-side); admin users paginated with load-more
- fix(web): chat cold-load defers machine list until composer focus; dedupe document queries in chat embed
- fix(web): unified nav — chat sidebar documents/feedback route to `/documents` and `/feedback`; workspace sidebar title from nav config
- fix(web): dashboard insight panels show inline error + retry; drilldown drawer focus trap and error state
- fix(web): chat ask retry; session list error; Thai Sources drawer copy
- fix(api): specialized/components list limit/offset (200 cap); sanitized operator-facing API errors
- fix(api): predictive `/health` requires auth and omits internal MCP URL; RCA 404 when machine missing
- fix(web): touch targets, documents empty vs no-results, ingest infinite machines, auth/signup Thai copy
- fix(web): employee welcome links to documents/repairs/inventory; HandoverCard gemini theme; WO mobile create drawer
- fix(web): inventory mobile factory switcher in no-factory banner; work-order status counts from single meta query
- fix(web): read-only employees access `/documents`, `/repairs`, `/inventory` via ReadWorkspaceLayout; inventory in shared nav config
- fix(web): AuthGuard slow-connection retry instead of 1.5s hard redirect
- fix(api): paginated `GET /documents` with infinite library hook and offline sync paging
- fix(api): server-side spare-parts sort (`sort_by` / `sort_dir`) wired to inventory UI
- fix(web): dashboard/chart defer on viewport; chat lazy session and indexed docs
- fix(web): Noto Sans Thai font stack; Thai operator copy in auth, chat, repairs, errors
- fix(web): 44px touch targets; dashboard/documents empty states; admin factories guard; ingest auth
- fix(web): landing lazy below-fold sections; hero respects reduced motion; Sign in on mobile
- fix(web): machines mobile form drawer + toast; work-order status tabs with counts
- fix(admin): password reveal modal on user create; grant read-all-factories preset
- fix(web): privacy sticky TOC; authenticated users can view `/`; account menu marketing link
- fix(web): FactorySwitcher confirm for “ทั้งหมด”; distinct Cog icon for machines nav
- fix(chat): attachment preview URL revoke after send; empty-state machine CTA
- fix(chat): employee “my feedback” open-count badge in sidebar
- fix(api): chat ask 2s dedupe window for identical session+question
- fix(chat): feedback report button uses server-assigned assistant message UUID from ask response
- fix(admin): create-user form and API; mutation errors surfaced in admin panels
- fix(scripts): seed_demo and provision_operator use employee/operator roles (not legacy viewer)
- fix(feedback): employees can list own submissions via `GET /feedback?mine=true` and chat sidebar tab
- fix(work-orders): status transitions (start/cancel), assignee column, and reassign in UI
- fix(auth): remove dead-end signup UI and show admin guidance for new accounts
- fix(auth): post-login redirect honors validated `?from=` deep links after password sign-in; middleware preserves query strings in return URL
- fix(auth): refuse to start API in production when `JWT_SECRET` is unset or still the dev placeholder
- fix(dashboard): period toggle (7/30/90d) now drives Problem Pulse and Symptom Trends widgets, not just other insight charts
- fix(auth): Thai onboarding copy, localhost-only demo credentials, faster unauthenticated redirect
- fix(web): read-only workspace redirect message, single dashboard privacy note, profile avatar alt text
- fix(web): landing background honors reduced motion and hides heavy orbs on mobile; defer service worker registration until after leaving `/`
- fix(web): admin page waits for `/auth/me` before rendering panels; chat welcome uses full name; session delete uses styled confirm dialog
- fix(web): distinct ClipboardList icon for work orders in workspace sidebar
- fix(dashboard): refresh button shows spinner and toast; Thai-only section headers
- fix(upload): document type labels in Thai; success banner links to jobs queue
- fix(feedback): error state includes retry action
- fix(work-orders): require description when creating a work order
- fix(landing): pause hero typing animation when browser tab is hidden
- fix(privacy): link back to landing page for logged-out visitors
- fix(layout): sync `html lang` per route (English landing/repairs/admin, Thai app shell)
- fix(documents): full-page empty state when no factory selected; RAG-aware delete confirm
- fix(upload): guard against double-submit while upload is in flight
- fix(admin): stacked factory access matrix on tablet (no horizontal scroll)
- fix(feedback): paginated inbox with load-more beyond 50 items
- fix(errors): sanitize FastAPI validation and internal detail strings for users
- fix(machines): paginated list with load-more; mobile card layout for actions
- fix(work-orders): paginated list with load-more; mobile card layout
- fix(repairs): lazy-load machine filter via infinite search; mobile repair cards
- fix(dashboard): slim top-at-risk fetch; defer heatmap, feedback gaps, and repair chart until in viewport
- fix(dashboard): activity feed uses factory-scoped incidents (no 500-machine prefetch)
- fix(feedback): dedicated `GET /feedback/count` for sidebar badge polling; allow `page_size=0` in paginated responses
- fix(landing): remove public demo credentials from marketing pages
- fix(security): verify JWT signatures in Next.js middleware and session cookie route
- fix(security): loud startup warning when AUTH_REQUIRED=false demo mode is active
- fix(admin): clarify that permission saves invalidate user sessions immediately via token_version
- fix(documents): byte-level download progress while PDF loads

### Added
- feat(web): `/inventory` workspace page wired to existing inventory components
- feat(api): `POST /api/v1/admin/users` for admin user creation with password
- feat(api): `assistant_message_id` on chat ask response for feedback linking
- docs: client handover [`docs/operations-guide.md`](docs/operations-guide.md)
- feat(chat): attach JPEG/PNG/WebP/PDF (max 10 MB, 3 files) in `/chat` — MinIO storage under `chat/`, OCR/PDF text inject into RAG context, compensating cleanup on extract failure, attachment chips in UI
- feat(web): chat speech-to-text — Web Speech API (Thai) with final/interim transcript merge, auto-restart (max 8 retries with backoff), mic preflight, secure-context check, and `กำลังฟัง…` / `กำลังรอเสียง…` status under the chat input; unit tests in `web/lib/speech/__tests__/transcript.test.ts`
- feat(storage): MinIO/S3 object storage for documents, machine cover images, and feedback photos — hierarchical keys (`factory/type/machine/...`), `STORAGE_BACKEND=s3`, Celery `materialize_local`, `/readyz` storage check, docker-compose MinIO service
- feat(api): `GET /factories` (RBAC-scoped) and admin factories panel; `GET/PATCH /auth/me` user profile with self-service display name and job position
- feat(web): `/account` settings page, login/landing UX polish (scroll reveal, background animation, workspace mode toggle)
- feat(ops): kcalsion factory deploy — `docker-compose.kcalsion.yml`, `.env.kcalsion.example`, nginx/cloudflared templates, `scripts/kcalsion-go-live.sh`, go-live docs
- feat(docker): `Dockerfile.web` build args for `NEXT_PUBLIC_*`; gemma profile uses `host.docker.internal:9090` for on-box proxy from containers
- feat(admin): `GET/PATCH /api/v1/admin/factories/{factory_id}/settings` + admin UI panel for RAG/ingest/notification tuning
- feat(ops): `handover_validate.py` runs chat_routing + RAG subset baseline gates; go-live `--validate` delegates to handover
- fix(ops): nightly full-LLM workflow fails on regression when `OLLAMA_BASE_URL` is configured
- fix(test): storage unit tests pin `storage_backend=local` for portable CI

## [0.6.0] — 2026-06-14

> **Factory handover & admin** — handover gate, public landing page, Neo rebrand, machine/IAM/work-order admin UI, and CI hardening since v0.5.0.

### Fixed
- fix(web): login onboarding — privacy before factory picker, admin auto-selects factory, session cookie errors surfaced when API is down
- fix(web): `/documents` no longer freezes client navigation — breadcrumb callback stabilized (infinite re-render loop)
- fix(web): machines page — per-row loading for ปลดระวาง/เปิดใช้งาน, optimistic status update, edit form scrolls into view; machine image upload button visible on hover
- fix(web): admin users, work orders, dashboard alerts — per-row action loading, forms/panels above tables, optimistic status updates where applicable
- fix(web): overlay stacking — account menu, settings, drawers, and modals portaled above sidebar (z-110); profile menu no longer clipped by sidebar overflow
- fix(web): workspace sidebar expand/collapse — width, labels, and main content animate in sync (richContent defer + slide transitions)
- fix(rag): document questions with analytic wording (เท่าไหร่ / how much) route to RAG when document context or `document_type` filter is present
- rebrand: product name **Neo Chat** replaces S.P.A.R.K./SPARK in UI, docs, API titles, RAG/analytics prompts, and PWA manifest (internal Python package `spark` and env vars `SPARK_*` unchanged)

### Added
- feat(ops): `scripts/handover_validate.py` — factory handover gate (upload → ingest → cited chat/RAG answer); `docker-compose.dev-app.yml` for API + Celery on local infra
- feat(e2e): live handover Playwright spec (`web/e2e/handover-flow.spec.ts`, `HANDOVER_E2E=1`) — admin upload + employee chat with sources
- feat(web): public GitHub-style landing page at `/` — pipeline, 15 doc types, deep-dive tabs, personas, Neo PWA, tech stack (from codebase)
- feat(ci): RAG baseline gate on PRs touching RAG/ingestion — Postgres, Redis, Qdrant services with `--deterministic-rag` eval (`configs/evaluation_baseline_ci.yaml`)
- feat(ci): web job runs `next build`; separate Playwright smoke E2E job with mocked API (`web/e2e/smoke.spec.ts`)
- feat(documents): `PATCH /api/v1/documents/{id}/visibility` to update job-position ACL after upload; workspace UI editor in document viewer
- feat(machines): `/machines` admin UI — create, edit, decommission machines; component PATCH; `include_inactive` list filter
- feat(admin): full user IAM editor — factory access, job positions, active toggle
- feat(work-orders): REST CRUD, `/work-orders` UI, assignable users API, HandoverCard on dashboard; Excel ingest config (`work_order.yaml`)
- test: mocked unit tests for `HandoverService` and `RCAService`; web offline LRU test via `npm test`
- refactor(rag): split `rag_service.py` into `src/spark/services/rag/` modules; 145-line compatibility facade

### Fixed
- fix(auth): production fail-closes auth — invalid/missing Bearer returns 401 when `APP_ENV=production` even if `AUTH_REQUIRED=false`
- fix(auth): factory-scoped RBAC on `/api/v1/components` and `/api/v1/specialized/*` (join Machine, `enforce_machine_access`)
- fix(auth): operator role routing in `middleware.ts` and write checks on insights/inventory endpoints (`can_write_factory`)
- fix(rca): parallel DB+RAG fetch, per-step timeouts, history fast-path, and RCAPanel abort/partial `top_causes` display (QA B1)
- fix(web): remove dead `AppShell`/`layout/Sidebar`; sync `package.json` to 0.5.0

### Changed
- chore(web): remove dead `OperatorRouteGuard` and `OPERATOR_BLOCKED_PATHS` — routing unchanged (`middleware.ts` remains source of truth)
- docs: refresh `architecture.md`, `qa-merged-report.md`, and `evaluation-baseline.md` for v0.5.0 routes and CI

### Backlog (P6+)
- P6: document metadata PATCH + explicit re-ingest endpoint
- P7: document approval queue (`pending_review`)
- P8: master-data audit log for machine/user changes

## [0.5.0] — 2026-06-14

> **UX/UI redesign** — chat-first Gemini workspace, documents learning hub, upload/admin flows, Neo branding, offline/PWA shell, and route guards.

### Added
- feat(rag): hybrid retrieval — Postgres chunk search mirror (migration 0025) merged with Qdrant vectors; config `RAG_HYBRID_RETRIEVAL_ENABLED`, `RAG_POSTGRES_LEXICAL_*`
- feat(ingest): generic `knowledge_document` type — supported PDF/Office/text/CSV files auto-route when no specific YAML match; text parser for `.txt`/`.csv`
- feat(analytics): temporal Text-to-SQL — relative date phrases (เดือนนี้, ไตรมาสที่แล้ว), improved semantic validation and fallback Thai messages
- feat(chat): follow-up context — prior turn machine/doc scope carries into multi-hop `/chat/{session}/ask`
- feat(web): dedicated `/upload` and `/documents` routes; workspace sidebar nav; Neo brand assets; upload ACL + job-position picker; ChatGuard/WriteGuard route protection
- feat(web): AI message actions (copy/regenerate), SparkMessageContent markdown rendering, documents hub hero and URL state hooks
- chore(scripts): `scripts/evaluate_baseline.py` + `configs/evaluation_baseline.yaml` — 40-case RAG/SQL E2E regression gate; docs in `docs/evaluation-baseline.md`
- chore(scripts): `scripts/dev.sh` sets `PYDANTIC_DISABLE_PLUGINS=1` for faster macOS startup

### Fixed
- fix(api): Celery worker health on `/readyz` — Redis broker ping + active worker inspect; returns `celery: unavailable` when no worker (HTTP 200 always)
- fix(rag): symptom+action queries (ร้อน/overheat/temperature + ต้องทำ/ขั้นตอน/วิธี) prefer `machine_manual`/`sop` over `repair_history` in rerank and evidence
- fix(ingest): PDF parser falls back to pdfplumber; scanned/image-only PDFs and missing OCR deps fail with explicit reason codes instead of false `completed`
- fix(ingest): qdrant-routed jobs fail when zero chunks are written; job-level IngestionError records reason codes such as `no_extractable_text`
- fix(qdrant): collection vector size follows active LLM embedding profile and fails clearly on dimension mismatch
- fix(ingest): repair history re-upload replaces prior rows via upsert instead of duplicate-key failures

### Added
- feat(api): ingest jobs API exposes progress, duration, page/chunk counts, and latest error metadata
- feat(web): ingest jobs table shows partial status, progress, and latest error metadata
- feat(rag): Thai-English factory term expansion and evidence scoring guardrails for cross-language manual retrieval
- feat(iam): job positions (`job_positions`, `user_job_positions`, `document_job_positions`) — document visibility by ตำแหน่งงาน (QC, QA, ช่าง ฯลฯ); unrestricted docs backward compatible
- feat(iam): permission roles `employee` / `operator` / `admin` (migrate จาก viewer/engineer/technician); OAuth default `employee`
- feat(iam): Admin API `/admin/users`, `/admin/job-positions`; `POST /auth/refresh`; JWT `job_position_ids` + `token_version` with cached verify (Redis/mem TTL)
- feat(web): upload form — factory select, machine picker, position multi-select; `/admin` user + position management; no-position banner from JWT
- **ACL v1:** factory + job position only — `machine_id` is metadata (not ACL); documented for future machine-scoped rules

### Added
- feat(web): อัปโหลดเอกสารสำหรับ admin (Dashboard) และ operator (แท็บเอกสาร) — `DocumentUploadPanel` บน hub/หมวด/เครื่อง/รายการทั้งหมด; operator ที่มีสิทธิ read ในโรงงานอัปโหลดได้
- feat(rag): cross-document reranking — widen retrieve (`RAG_RETRIEVE_MULTIPLIER`), document-level scoring (`RERANKER_STRATEGY=cross_document`), aligned relevance/source scores
- feat(analytics): Text-to-SQL semantic validation — LLM-as-Judge + reverse verification LangGraph node; `judge` LLM profile; config flags `SQL_SEMANTIC_VALIDATION`, `SQL_REVERSE_VERIFICATION`
- feat(cache): verified Q&A cache (`verified_qa_cache` migration 0020) — factory-wide similar-question reuse with RBAC on `source_doc_ids`; `cache_hit` API + **ยืนยันแล้ว** badge
- Prometheus: `spark_rag_doc_rerank_seconds`, `spark_sql_judge_pass_total`, `spark_qa_cache_hit_total`, `spark_qa_cache_rbac_reject_total`

### Changed
- docs: drop product "v3" branding — use Neo Chat and semver tags (`v0.5.x`) only
- fix(ingest): อนุญาต `POST /ingest/file` สำหรับ factory access ระดับ read (ช่างอัปโหลดเอกสารได้โดยไม่ต้อง write)

### Fixed
- fix(chat): แยก chat session ตาม `user_id` (list/create/ask/messages); sidebar กรองแชทว่าง orphan (`for_sidebar` + `message_count`); reuse แชทว่าง; label แชท legacy
- fix(web): **GeminiWorkspaceNav** สลับ Chat ↔ Dashboard สำหรับ admin/write

### Added
- chore(scripts): `scripts/e2e_smoke_flows.py` — API smoke สำหรับ chat/sessions/insights/documents

### Added (prior)
- feat(chat): auto-title sessions (heuristic + LLM fallback), pin/rename/delete ใน sidebar; `PATCH /chat/sessions/{id}`; migration 0018
- feat(insights): Phase 2 — LLM topic tagging (Celery nightly + backfill), hotness alerts (`insights_hotness`), dashboard badge; migration 0019
- feat(insights): Problem Trends Dashboard — `/dashboard` สำหรับแอดมิน (write+); Problem Pulse, เทรนด์คำถาม AI, อาการซ่อม, heatmap, feedback gaps + drill-down คำถามดิบ
- feat(web): Offline-First Mode — cache PDF ใน IndexedDB (cache-on-read + prefetch สูงสุด 5 ไฟล์ต่อเครื่อง, Wi‑Fi only), เปิดเอกสารออฟไลน์ได้, metadata เอกสาร/เครื่องจักร, feedback outbox ส่งเมื่อเน็ตกลับ
- feat(web): PWA ติดตั้งได้ — ไอคอน 192/512, manifest ครบ (scope/id), middleware เปิด public path, SW v2, ปุ่ม **ติดตั้งแอป** ใน Settings
- feat(web): `OfflineStatusBar`, Settings พื้นที่ cache / Wi‑Fi-only / ล้าง cache, PWA manifest + service worker (shell เท่านั้น)
- feat(api): `ETag` / `304` บน `GET /documents/{id}/file` สำหรับ revalidate cache; `file_hash_sha256` ใน document list
- feat(feedback): Floor Feedback Loop — ช่างส่งคอมเมนต์+รูปจากเอกสาร/คำตอบ RAG (`POST /feedback`); แอดมิน triage ในแท็บ sidebar **แจ้งกลับ** พร้อม badge จำนวน `open`
- feat(api): `GET/PATCH /feedback`, stream attachments, factory RBAC (read ส่งได้ / write+ inbox)
- feat(web): `FeedbackReportModal` + ปุ่ม **เสนอแนะการแก้ไข** ใน DocumentViewer, DocumentRow, คำตอบ AI, Sources drawer
- feat(web): แท็บ **เอกสาร** Learning Hub — หมวดหลัก (เครื่องจักร / ความรู้ / ความปลอดภัย ฯลฯ), grid เครื่องจักรพร้อมรูป, หน้าเรียนรู้ต่อเครื่อง, breadcrumb, deep link `?view=documents&machine=&doc=`, ปุ่ม **ถาม AI เกี่ยวกับเครื่องนี้**
- feat(web): mock รูปปกเครื่องจักรจาก `public/machines/placeholders/*.jpg` (รูปเครื่องจักรจริง) ตาม `machine_type` — แสดงเมื่อยังไม่อัปโหลดรูปเอง
- fix(web): PDF viewer responsive — `react-pdf` ปรับความกว้างตามหน้าจอ, โหลดทีละชุดหน้า, worker เวอร์ชันตรงกัน, dynamic import, fallback iframe
- feat(api): อัปโหลดรูปปกเครื่องจักร — `POST/GET/DELETE /machines/{id}/image` (JPEG/PNG/WebP, 2MB)
- feat(documents): Document Library MVP — `StorageBackend` (local disk), secure `GET /documents/{id}/file`, factory-scoped access + audit log, RAG pre-filter by `doc_id` with source view links
- fix(documents): resolve MIME from filename for legacy rows (`mime_type` NULL); audit log no longer 500 when JWT user is absent from `users` table (dev/system principal)
- feat(web): แท็บ **เอกสาร** ใน chat sidebar — `DocumentsPanel`, PDF `DocumentViewer` (react-pdf), อัปโหลดผ่าน ingest form, ปุ่ม **เปิดเอกสาร** จาก RAG sources
- feat(auth): Google OAuth sign-in with domain allowlist and optional password-login toggle
- feat(web): Gemini-style chat UI as primary experience — `/chat`, Google auth flow, settings modal
- docs: `TEAM_SYSTEM_OVERVIEW.md` — Thai team onboarding guide
- chore(cursor): GitHub workflow rules v2 (autopilot, CI/CD, releases)
- chore: root `package.json` dev shortcuts; demo scripts for presentation and OAuth repair
- feat(web): factory-scoped UI — `factory_id` URL param, scope badge, query invalidation on factory switch, machine filter reset
- feat(web): operator route guard — read-only operators blocked from ingest/analytics/inventory pages
- feat(web): analytics machine multi-select filter; ingest job summary panel and improved drag-and-drop upload
- feat(web): ClientPortal for modals; Repair History chart refactor
- scripts/seed_demo_bulk.py — idempotent bulk demo seed (factories, machines, repairs, inventory, users)
- scripts/demo_bulk_templates.py — fixture templates for bulk seed profiles
- feat(api): factory_id enforcement on analytics, inventory, jobs, documents, and RAG endpoints
- feat(rag): structured source metadata in RAG response schema
- feat(web): KPI month-over-month delta badges on Dashboard repair summary and Inventory stock value
- feat(web): Plant Insights panel — 12-month Repair History chart (repairs, downtime, cost) + Top at-risk machine list with last PM
- feat(web): Repair History chart — 3M/6M/12M/YTD range selector, dual Y-axis for cost, hover tooltip, toggleable legend
- feat(web): `/dashboard/status-preview` — compare six Machine Status panel variants
- feat(web): Repair History "Ask AI" row action — opens RAG Chat with machine scope and editable Thai prompt via `/rag-chat`
- ops: `prometheus.local.yml` + Grafana provisioning-local for Homebrew observability when Docker is unavailable
- feat(ingest): store original upload filename on ingestion jobs; FILE column in job history; drag-and-drop upload zone with English labels
- feat(web): Repair History close form — PATCH root cause when closing a job; separate symptom/root-cause filters
- scripts/dev.sh — one command to run API + Celery + Next.js after docker infra
- scripts/fix_future_repair_dates.py — clamp future repair_history dates from Excel ingest
- feat(inventory): inline Reorder button on LOW-stock parts, reorder modal, `POST /reorder-requests`, clickable stock-value KPI

### Changed
- feat(web): replace legacy `(shell)` dashboard routes with chat-first navigation
- feat(web): Plant Overview redesign — industrial slate palette, simplified layout (insights + observability + machine grid)
- feat(web): seed_demo — repair cost/downtime trend data for dashboard chart

### Fixed
- fix(insights): hotness formula capped + is_new_signal; heatmap sqrt scale + legend; privacy note on dashboard
- docs: `docs/insights-dashboard.md` — timezone, cache strategy, token cost; Phase 2 hotness threshold alerts (not MVP)
- fix(web): hide empty Grafana optional metric cards on Dashboard; dev/admin see muted placeholders
- fix(inventory): DEAD stock status in parts catalog — gray badge, KPI filter, separate dead-stock toggle (aligned with 180d no-movement rule)
- fix(web): Top at-risk panel — fetch top 5 from `/predictive/at-risk`, dynamic count, next PM, repair-history links
- fix(web): RAG Chat sources panel shows indexed documents when idle; machine scope from URL/sidebar; thinking indicator
- fix(observability): sanitize Prometheus NaN/Inf so `/observability/overview` returns 200
- fix(predictive): clamp negative risk scores when repair dates are in the future
- fix(web): Repair History root cause column — distinct from symptom; badge รอวิเคราะห์ when empty; seed no longer copies symptom into root_cause
- fix(web): dashboard at-risk count, chat message sync race, risk % display; repair chart page_size capped at API max (200)
- fix(ingestion): cap future repair_date values at ingest time; re-queue duplicate file upload instead of 500
- fix(dev): bootstrap_dev Celery/API use PYTHONPATH=src

### Removed
- feat(web): Command Center panel, plant map, donut/gauge charts (replaced by repair history + top at-risk)
- feat(web): ROI Pillars panel on Plant Overview (reverted — dashboard stays focused on maintenance risk + metrics)

## [0.4.4] — 2026-05-29

### Added
- test(demo): `predictive/at-risk` check in demo_validate.py

### Changed
- docs: README.th.md and demo_playbook synced to v0.4.3 architecture

### Removed
- chore(repo): untrack internal `ข้อมูล/` pitch files from git

## [0.4.3] — 2026-05-29

### Added
- CI/CD: GitHub Actions on `develop` and `main` (ruff, pytest, web tsc + ESLint)
- `GET /api/v1/observability/overview` — Prometheus metrics on Plant Overview dashboard
- Merged Ingestion + Job History at `/ingest`
- `develop` branch integration flow before `main` releases

### Changed
- Remove machine sensor telemetry API, Operations Feed, and optimization web UI
- Dashboard: Maintenance Risk from repair history + Grafana app metrics (not live sensors)
- Truth naming: Repair History, Plant Overview, App Metrics (Grafana)
- Dashboard summary uses `/predictive/at-risk` only (no client alerts SSE)
- Server redirects for legacy `/alerts`, `/optimization`, `/jobs`
- README, runbook, and integrations docs synced to current architecture

### Removed
- `POST /api/v1/telemetry/events`, `sensor_readings`, `alert_rules`, `telemetry_events`, `optimization_advisories`
- `optimization_service`, Dify advisory client, `mock_telemetry.py`, optimization YAML configs
- Web alerts/optimization pages and SSE stream providers

### Fixed
- CI: `alembic upgrade head` before pytest; `SPARK_TESTING` NullPool for async test stability
- ESLint config for non-interactive web lint in CI

## [0.4.2] — 2026-05-24

### Added
- Inventory insights, shift handover, RCA assistant, cross-encoder reranker
- Sidecar orchestration scripts and factory deployment overlay

## [0.4.1] — 2026-05-24

### Added
- Factory-scoped RBAC enforcement, sharding integration tests, golden QA gate

## [0.4.0] — 2026-05-24

### Added
- JWT auth, Qdrant per-factory sharding, predictive PoC, SSE alerts, web UI redesign
- Production integrations (RAGFlow, MCP, DeepAnalyze adapters)

## [0.3.0] — 2026-05-24

### Added
- Platform architecture: config-driven ingestion, RAG fallback ladder, chat orchestrator, Text-to-SQL analytics
- 12 document-type YAML configs (PDF, Excel, Word, JSON, OCR parsers)
- Celery workers, Redis cache, lexical reranker, Prometheus metrics
- P3 modules: RBAC/JWT middleware, inventory, partitioned tables, predictive maintenance PoC
- Next.js UI Lite (chat, ingest, jobs, machines pages)

### Fixed
- fix(ingestion): stream large PDFs with pypdf, validate metadata from document_context
- fix(rag): restore retrieval when only_active excluded all docs
- fix(rag): synthesis fallback for small local LLM (qwen2.5:3b)
- fix(rag): route overheating queries to machine_manual, not unrelated repair_history

### Changed
- revert: removed GitHub Actions workflows and Dependabot (out of project scope)

## [0.2.0] — prior foundation release

### Added
- PostgreSQL schema migrations 0001–0005
- Qdrant collection with payload indexes
- Master data CRUD (factories, machines, components, aliases)
- Demo seed scripts and runbook
