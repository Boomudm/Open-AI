# GitHub release notes archive — removed 2026-07-18

Bodies of the 8 GitHub Releases deleted in the 2026-07-18 versioning cleanup
(tags removed; see `release-tags-2026-07-18.md`). Content is largely a copy of
the matching `CHANGELOG.md` sections, preserved here verbatim for completeness.

### v1.0.0
**v1.0.0 — Enterprise handover** — 2026-06-19T21:01:30Z

## [1.0.0] — 2026-06-20

> **Enterprise handover release** — on-prem deployment kit, Thai localization, super-admin ops, pre-flight security audit, repository spring-clean, and GitHub enterprise standards (CONTRIBUTING, SECURITY, CodeQL, Dependabot). Production-ready for factory LAN delivery.

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
- fix(rag): machine-scoped retrieval with factory-wide chunks; off-topic eval guard; SOP LOTO context ordering
- fix(web): E2E smoke Thai sidebar labels; `useEffect` cleanup in landing hero and service worker
- fix(ci): SQL RLS integration test seed guard; deterministic eval LLM mock


### v0.8.1
**v0.8.1 — Post-v0.8.0 polish (~92/100)** — 2026-06-19T07:48:06Z

## [0.8.1] — 2026-06-19

> **Post-v0.8.0 polish** — Production Readiness ~92/100; feedback source linking, notification smoke test, factory defaults.

### Added
- feat(feedback): auto-link `doc_id`/page จาก chat message sources; clickable sources ใน quality-failures + feedback drawer
- feat(notifications): `inventory_report_ready` event เมื่อรายงานสต๊อกเสร็จ; `handover_validate.py --notify-test` + `kcalsion-go-live.sh --notify-test`
- chore(factory): `INGEST_BACKEND=auto` default ใน `docker-compose.factory.yml`

### Changed
- docs: checklist/roadmap sync v0.8.1 · ~92/100; kcalsion go-live ใช้ `main` + tag v0.8.x

### v0.8.0
**v0.8.0 — Enterprise Phase 5 closure** — 2026-06-19T07:29:09Z

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

### v0.7.0
**v0.7.0 — Enterprise chat & ingest platform** — 2026-06-19T06:12:35Z

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



### v0.6.0
**v0.6.0 — Factory handover & admin** — 2026-06-14T13:47:03Z

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


### v0.5.0
**v0.5.0** — 2026-06-14T05:07:16Z

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
- docs: drop product "v3" branding — use S.P.A.R.K. and semver tags (`v0.5.x`) only
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



### v0.4.4
**v0.4.4 — Executive ROI & Demo Polish** — 2026-05-29T05:16:15Z

## Highlights

- **ROI Pillars** panel on Plant Overview — 5 use cases with live KPIs and deep links
- **Docs:** README.th.md and demo_playbook synced to v0.4.3+ architecture
- **Demo:** `demo_validate.py` adds `predictive/at-risk` check
- **Repo hygiene:** internal `ข้อมูล/` pitch files removed from git tracking

## Try it

```bash
git pull origin main
cd web && npm run dev
# Open http://localhost:3000/dashboard
python scripts/demo_validate.py
```

Full notes: [CHANGELOG.md](https://github.com/CPF-Chula-CEDT-2026/spark/blob/main/CHANGELOG.md)

### v0.4.3
**v0.4.3 — Platform refactor** — 2026-05-29T05:04:13Z

## Highlights

- **CI/CD:** GitHub Actions on `develop` and `main` (Python ruff/pytest, web TypeScript/ESLint)
- **Dashboard:** Plant Overview with Grafana app metrics + Maintenance Risk from repair history
- **Removed:** Machine sensor telemetry API, Operations Feed, optimization UI, dead backend code
- **UX:** Truth naming (Repair History, etc.), merged Ingestion + Job History, legacy route redirects

## Upgrade

```bash
git pull origin main
alembic upgrade head   # migrations 0008, 0009
```

## Breaking changes

- `POST /api/v1/telemetry/events` removed
- Web `/optimization`, `/alerts` redirect to dashboard; `/jobs` → `/ingest?tab=jobs`
- Tables dropped: `sensor_readings`, `alert_rules`, `telemetry_events`, `optimization_advisories`

Full notes: [CHANGELOG.md](https://github.com/CPF-Chula-CEDT-2026/spark/blob/main/CHANGELOG.md)

