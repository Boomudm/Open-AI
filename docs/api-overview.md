# API Overview

The Neo Chat API is a FastAPI backend under `/api/v1`, made up of 19 router
modules (~96 routes total). Interactive docs are always available at
`/docs` (Swagger UI) and `/redoc`; `/openapi.json` is the machine-readable
spec. Root-level (non-versioned) endpoints exist for health/ops: `/`,
`/healthz`, `/readyz` (`?lite=1` / `?deep=1`), and `/metrics` (Prometheus).

For **how to authenticate as an external/partner integration**, see
[`docs/public-api-integration.md`](./public-api-integration.md) — that
doc covers API keys, error codes, and exposing the API outside the LAN in
depth and isn't repeated here. For **what each admin endpoint does in the
UI**, see [`docs/admin-guide.md`](./admin-guide.md).

> **Correction to older docs:** answers are **not** produced exclusively
> from uploaded documents. In addition to the document-grounded RAG path,
> the API supports a read-only **Text-to-SQL** path against an
> admin-registered external Postgres database
> (`/api/v1/admin/data-sources`, routed through chat via
> `ChatOrchestrator`) — see
> [Architecture § How a question gets answered](./architecture.md#how-a-question-gets-answered).

## Authentication

| Method | How | Typical caller |
| --- | --- | --- |
| JWT bearer token | `Authorization: Bearer <jwt>`, obtained from `/auth/login` or `/auth/oauth/exchange` | The web UI, after login |
| API key | `Authorization: Bearer nk_...`, issued by an admin | Server-to-server / partner integrations |
| SSE stream ticket | Single-use ticket appended to an `EventSource` URL | Browser SSE connections only (can't set custom headers) — not needed when calling with an API key |
| Demo mode | None — every request runs as a built-in super-admin principal when `AUTH_REQUIRED=false` | Local/offline demos only, never production |

Every error response uses one envelope shape:
`{"detail", "code", "trace_id", ...}`.

## Route groups

### Auth — `/api/v1/auth`

Login, Google OAuth, session/profile management. No auth required for
`login`, `oauth/exchange`, `google/status`, `google/login`,
`google/callback`; everything else requires a valid token.

| Route | Method | Purpose |
| --- | --- | --- |
| `/auth/login` | POST | Email + password → JWT |
| `/auth/oauth/exchange` | POST | Exchange a Google OAuth code for a JWT |
| `/auth/google/login`, `/auth/google/callback`, `/auth/google/status` | GET | Google OAuth flow |
| `/auth/me` | GET / PATCH | Read or update the current user's profile |
| `/auth/me/profile-picture` | POST / DELETE | Upload/remove avatar |
| `/auth/profile-picture/{user_id}` | GET | Fetch another user's avatar |
| `/auth/privacy-acceptance` | POST | Record privacy-policy acceptance (required before first use) |
| `/auth/job-position` | POST | Self-service job-position selection on first login |
| `/auth/change-password` | POST | Change the current user's password |
| `/auth/refresh` | POST | Refresh an access token |

### Chat — `/api/v1/chat` (the product's core)

Session-based, document-grounded Q&A with streaming and citation support.

| Route | Method | Purpose |
| --- | --- | --- |
| `/chat/capabilities` | GET | What the chat backend currently supports (feature flags) |
| `/chat/sessions` | GET / POST | List or create chat sessions |
| `/chat/sessions/{id}` | PATCH / DELETE | Rename/update or delete a session |
| `/chat/{session_id}/ask` | POST | Ask a question — non-streaming; add `"stream": true` for SSE |
| `/chat/{session_id}/messages` | GET | Paginated message history |
| `/chat/{session_id}/snapshots` | GET | Session slot-state snapshots (machine lock, revision, pipeline stickiness over time) |
| `/chat/{session_id}/messages/{message_id}/retrieval-snapshot` | GET | The retrieval evidence a specific answer was grounded in — the audit trail for one answer |
| `/chat/{session_id}/messages/{message_id}/attachments/{sort_order}` | GET | Stream a chat attachment |
| `/chat/messages/{message_id}/verify` | POST | Mark an answer verified/correct (feeds the verified-QA cache) |

See [Architecture § How a question gets answered](./architecture.md#how-a-question-gets-answered)
for what happens between `ask` and the response.

### RAG — `/api/v1/rag` (stateless variant)

A stateless equivalent of `/chat/{session_id}/ask` for callers that don't
want to manage a session — this is what
[`docs/public-api-integration.md`](./public-api-integration.md) uses for
simple single-shot Q&A.

| Route | Method | Purpose |
| --- | --- | --- |
| `/rag/query` | POST | Ask a question, get one JSON answer with sources — no session required |
| `/rag/preflight` | POST | Check whether a question/filter combination is likely to be answerable before spending a full query |
| `/rag/health` | GET | Lightweight RAG-subsystem health check |

### Documents — `/api/v1/documents`

The document library: browse, fetch, and manage visibility of already
uploaded/indexed documents. Uploading and ingest-job tracking are separate
route groups (below).

| Route | Method | Purpose |
| --- | --- | --- |
| `/documents` | GET | Paginated document library, filterable |
| `/documents/{doc_id}` | GET | Document metadata |
| `/documents/{doc_id}/file` | GET | Stream the original file |
| `/documents/{doc_id}/visibility` | PATCH | Change job-position-restricted visibility |
| `/documents/{doc_id}` | DELETE | Remove a document |
| `/documents/{doc_id}/policy-findings` | GET | Content-safety scanner findings for a quarantined document (part of `document_release.py`) |
| `/documents/{doc_id}/release` | POST | Release a quarantined document for indexing — see [Admin Guide § Document release](./admin-guide.md#document-release-quarantine-review) |

### Ingestion — `/api/v1/ingest*`

Upload and process new documents. Spans three route files
(`ingest.py`, `ingest_preflight.py`, `jobs.py`) sharing the `/ingest`
prefix.

| Route | Method | Purpose |
| --- | --- | --- |
| `/ingest/document-types` | GET | List the 13 configured document-type profiles |
| `/ingest/preflight` | POST | Validate a file/type combination before committing to a full upload |
| `/ingest/file` | POST | Upload a file — returns `202` and an ingest job to poll/stream |
| `/ingest/documents/{doc_id}/reingest` | POST | Re-run ingestion for an already-indexed document (blue-green swap) |
| `/ingest/jobs` | GET | List ingest jobs |
| `/ingest/jobs/{job_id}` | GET | One job's status |
| `/ingest/jobs/{job_id}/errors` | GET | Structured errors for a job |
| `/ingest/jobs/{job_id}/stream` | GET | SSE stream of job progress |
| `/ingest/jobs/{job_id}/retry` | POST | Retry a failed job |

### Machines — `/api/v1/machines`

The machine registry referenced by chat "lock to this machine" and by
document tagging.

| Route | Method | Purpose |
| --- | --- | --- |
| `/machines` | GET / POST | List or create machines |
| `/machines/{machine_id}` | GET / PATCH / DELETE | Read, update, or remove a machine |
| `/machines/{machine_id}/image` | GET / POST / DELETE | Machine photo |
| `/machines/{machine_id}/aliases` | POST | Add an alternate name/ID for a machine (helps retrieval match different naming conventions) |

### Feedback — `/api/v1/feedback`

Report and triage incorrect/incomplete chat answers — see
[Admin Guide § Feedback triage](./admin-guide.md#feedback-triage-feedback)
for the status lifecycle.

| Route | Method | Purpose |
| --- | --- | --- |
| `/feedback` | GET / POST | List (inbox) or submit feedback, with optional photo attachments |
| `/feedback/count` | GET | Open-feedback count, e.g. for a badge |
| `/feedback/{id}` | GET / PATCH | Read or triage one item (status, resolution note) |
| `/feedback/{id}/attachments/{sort_order}` | GET | Stream an attached photo |

### Factories & Job Positions (read-only, general use)

Non-admin, RBAC-filtered lookups — every authenticated user can call
these; results are scoped to what they can see.

| Route | Method | Purpose |
| --- | --- | --- |
| `/factories` | GET | Factories the caller has any access to (all of them, for admins) |
| `/job-positions` | GET | Active job positions (for the position-selection step at signup) |

The admin CRUD equivalents live under `/admin/factories` and
`/admin/job-positions` — see below.

### Admin — `/api/v1/admin*`

Requires the `admin` role (or `is_super_admin`) unless noted. Fully
documented, tab by tab, in [`docs/admin-guide.md`](./admin-guide.md) — this
is just the route map.

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/users` | GET / POST | List / create users |
| `/admin/users/{id}` | PATCH | Update role, active state, factory access, job positions, or (super-admin only) `is_super_admin` |
| `/admin/users/{id}/promote-operator` | POST | Shortcut: promote an employee to operator |
| `/admin/job-positions` | GET / POST | List / create job positions |
| `/admin/job-positions/{id}` | PATCH | Update or deactivate a job position |
| `/admin/job-positions/{id}/usage` | GET | Document/user counts referencing a position |
| `/admin/factories` | GET / POST | List / create factories |
| `/admin/factories/{id}` | DELETE | Delete a factory (**super admin only**, factory must be empty) |
| `/admin/factories/{id}/settings` | GET / PATCH | Per-factory RAG/ingest/notification settings |
| `/admin/data-sources` | GET / POST | List / register external Postgres data sources (Text-to-SQL) |
| `/admin/data-sources/test` | POST | Test raw connection params before saving |
| `/admin/data-sources/{id}` | GET / PATCH / DELETE | Manage one data source |
| `/admin/data-sources/{id}/test` | POST | Test an already-saved data source's connection |
| `/admin/data-sources/{id}/discover` | GET | Introspect the remote schema |
| `/admin/data-sources/{id}/tables` | PUT | Save the allow-listed tables + factory/position scoping |
| `/admin/api-keys` | GET / POST | List / issue API keys |
| `/admin/api-keys/{id}/revoke` | POST | Revoke a key (keeps the audit row) |
| `/admin/api-keys/{id}` | DELETE | Delete a key entirely |
| `/admin/audit/export` | GET | CSV retrieval-log export |

### System Admin — `/api/v1/system-admin`

Powers the Control Room dashboard — see
[Admin Guide § System Admin / Control Room](./admin-guide.md#system-admin--control-room-system-admin).

| Route | Method | Purpose |
| --- | --- | --- |
| `/system-admin/dashboard` | GET | The full operational snapshot (traffic, LLM usage, Qdrant/Postgres/storage/worker stats, circuit breaker state, incidents, …) |
| `/system-admin/actions/clear-cache` | POST | Flush Redis cache |
| `/system-admin/actions/qdrant-sync` | POST | Enqueue a Postgres↔Qdrant reconciliation job |
| `/system-admin/actions/maintenance` | POST | Toggle maintenance mode, with an optional user-facing message |
| `/system-admin/actions/reset-agentic-circuit` | POST | No-op today — the agentic circuit isn't wired up in this delivery |
| `/system-admin/actions/reset-rag-circuit` | POST | Manually close the RAG circuit breaker |

### Audit — `/api/v1/audit`

The **compliance** export — distinct from `/admin/audit/export` above; see
[Admin Guide § Audit exports](./admin-guide.md#audit-exports) for the
difference.

| Route | Method | Purpose |
| --- | --- | --- |
| `/audit/export` | GET | JSON compliance bundle: redacted retrieval log + WORM audit chain with integrity confirmation, requires `compliance_officer` role or admin |

### Streams — `/api/v1/streams`

| Route | Method | Purpose |
| --- | --- | --- |
| `/streams/ticket` | POST | Issue a single-use SSE ticket for browser `EventSource` connections (not needed when calling with an API key directly) |

## OpenAPI tag groups

The routes above map to 13 OpenAPI tags for browsing in `/docs`: **Auth,
Chat, RAG, Documents, Ingestion, Machines, Factories, Job Positions,
Feedback, Admin, System Admin, Audit, Streams.**

## Related docs

- [docs/public-api-integration.md](./public-api-integration.md) — partner/external integration guide (API keys, exposing the API, error codes)
- [docs/admin-guide.md](./admin-guide.md) — what each admin endpoint does in the UI, and the permission model
- [docs/architecture.md](./architecture.md) — how a chat request actually flows through the system
- [docs/user-guide.md](./user-guide.md) — the operator-facing feature guide
