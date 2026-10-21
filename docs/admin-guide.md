# Admin Guide

This guide covers everything an **admin** (`role: admin`, or the separate
`is_super_admin` flag) can do in Neo Chat: user and access management,
factory setup, document release, feedback triage, external database
connections for Text-to-SQL, API keys, and the System Admin / Control Room
operational dashboard.

It's written from the actual admin API (`src/spark/api/v1/endpoints/admin*.py`,
`feedback.py`, `document_release.py`, `system_admin.py`, `audit_export.py`)
and the admin UI (`web/app/admin/`, `web/app/admin/factories/`,
`web/app/system-admin/`, `web/app/feedback/`, `web/components/admin/`) — if
this guide and the UI ever disagree, trust the UI and the code.

## Contents

- [Roles & permissions model](#roles--permissions-model)
- [Signing in as an admin](#signing-in-as-an-admin)
- [Admin console: `/admin`](#admin-console-admin)
  - [Users tab](#users-tab)
  - [Job Positions tab](#job-positions-tab)
  - [External Postgres tab (Text-to-SQL)](#external-postgres-tab-text-to-sql)
  - [API keys tab](#api-keys-tab)
- [Factory management: `/admin/factories`](#factory-management-adminfactories)
- [Document release (quarantine review)](#document-release-quarantine-review)
- [Feedback triage: `/feedback`](#feedback-triage-feedback)
- [System Admin / Control Room: `/system-admin`](#system-admin--control-room-system-admin)
- [Audit exports](#audit-exports)
- [Permission reference](#permission-reference)
- [Common admin recipes](#common-admin-recipes)
- [Gotchas and non-obvious behavior](#gotchas-and-non-obvious-behavior)

## Roles & permissions model

Every authenticated request carries a `Principal` (`src/spark/core/security.py`)
with a **role tuple**, a **per-factory access map**, and a separate
**`is_super_admin` boolean**. These are independent axes — a user's overall
permission is the union of all three.

### Base roles

| Role | Set via | Meaning |
| --- | --- | --- |
| `employee` | Admin → Users tab, default for new accounts | Read access only, scoped to whatever factories/job positions are granted |
| `operator` | Admin → Users tab, or the "Promote to Operator" button | Automatically gets **write** access to every factory it's granted (not just read) |
| `admin` | Admin → Users tab | Full read/write on everything, bypasses factory-access checks, can reach `/admin` and `/system-admin` |

A user's `roles` list is **replaced wholesale** on every update — the admin
UI only ever assigns exactly one of the three roles above at a time
(`_set_user_role` in `admin.py` deletes all existing `UserRole` rows first).
There is no "employee + operator" combination.

### `release_documents` role — exists in code, not exposed in the UI

`can_release_documents()` (`security.py`) accepts either `is_admin` **or**
`"release_documents" in p.roles`. The Users tab's role selector only offers
`employee` / `operator` / `admin`, so today the only way anyone gets
`release_documents` is to be an `admin` — the granular role exists in the
RBAC model and would need to be granted via a direct API/DB change (or a
future UI addition) to use it without also granting full admin.

### Factory access levels

| Level | Grants |
| --- | --- |
| `read` | View documents/chat scoped to that factory |
| `write` | Upload, release documents (if also `release_documents`/admin), submit feedback |
| `admin` | Same practical effect as `write` today in most checks, reserved for future finer-grained control |

Granting `write` access via factory access on an `employee` does **not**
give them the write behaviors that the `operator` role gives automatically
— `can_write_factory()` short-circuits `True` for any `operator`, but for an
`employee` it checks the explicit per-factory grant.

### Super admin (`is_super_admin`)

A separate boolean, independent of `roles`. It currently gates exactly one
extra thing in the UI: **deleting a factory** (`AdminFactoriesPanel.tsx`
calls `isSuperAdminUser()` to show the delete button; the backend endpoint
`DELETE /admin/factories/{id}` uses `require_super_admin()`). A super admin
is also implicitly treated as admin everywhere else (`Principal.is_admin`
returns `True` if `is_super_admin` is set).

**There is no UI to grant `is_super_admin`.** The API supports it
(`PATCH /api/v1/admin/users/{id}` with `is_super_admin: true`), and only an
existing super admin may call it (`actor.is_super_admin` is checked
server-side), but the Users tab's edit form does not expose this field. To
promote someone to super admin today, an existing super admin has to call
the API directly (e.g. with `curl` and a bearer token) — see
[Common admin recipes](#common-admin-recipes).

### Session invalidation on permission changes

Any change to a user's role, active status, factory access, or job
positions calls `bump_user_token_version()`, which invalidates their
current session immediately. The UI surfaces this as: *"Saved — the user's
session was ended immediately (their next API call will need to sign in
again)."* This is not a bug — it's intentional, so a demoted or
deactivated user can't keep using a stale token.

## Signing in as an admin

Admin pages are client-side gated: `/admin`, `/admin/factories`, and
`/system-admin` each fetch `GET /api/v1/auth/me`, check
`profile.roles.includes("admin")` (or `is_super_admin` for
`/system-admin`), and redirect to `/chat` if the check fails while showing a
brief "checking admin permission…" loading state. The server-side
endpoints re-check the role independently — the frontend gate is a UX
convenience, not the actual security boundary.

If `AUTH_REQUIRED=false` (demo mode — see
[03 — Known Limitations](./DELIVERY_ACCEPTANCE.md)), every request runs as
the built-in `SYSTEM_PRINCIPAL`, which has `roles=("admin",)` and
`is_super_admin=True` — i.e. **everyone is a super admin**. Never run demo
mode outside a local/offline sandbox.

## Admin console: `/admin`

Four tabs, each backed by its own component and its own set of endpoints.
There is **no "Feedback" tab here** — feedback triage moved to its own page,
[`/feedback`](#feedback-triage-feedback).

### Users tab

**Create a user** (`+ เพิ่มผู้ใช้` / "Add user"):

| Field | Notes |
| --- | --- |
| Email | Required, must be unique |
| Full name | Optional |
| Username | Optional — auto-derived from the email local-part if left blank (e.g. `narin.y@x.com` → `narin_y`, with a `_2`, `_3`, … suffix on collision) |
| Temporary password | Required, minimum 8 characters — shown to you **once** in a modal right after creation so you can hand it to the user; the API never returns it again |
| Access level | `employee` / `operator` / `admin` |
| Factory access | Per-factory dropdown: none / read / write / admin. "Grant read to all factories" is a one-click shortcut |
| Job positions | Multi-select checkboxes — controls which job-position-scoped documents the user can see |

**Edit a user**: same fields minus password, plus an **Active** checkbox.
Deactivating (`is_active: false`) does not delete the account — it blocks
login and (via the token-version bump) kills any live session immediately.

**Promote to Operator**: a one-click button shown only for users whose
current role is `employee`. It sets the role to `operator` **and** upgrades
any existing `read`-level factory grants to `write` in the same call
(`promote_operator` in `admin.py`) — it does not touch factories where the
user has no access at all.

### Job Positions tab

Job positions are the mechanism behind "document access restricted to
certain roles" (e.g. a document marked visible only to `qc` and
`maintenance` positions). Fields on creation: a lowercase slug `position_code`
(regex `^[a-z][a-z0-9_]{1,48}$`, e.g. `qc`) and a Thai display name.

There is **no delete** — only **deactivate**. Deactivating asks for
confirmation and first calls `GET /admin/job-positions/{id}/usage` to show
you exactly how many documents and users are tied to it, e.g.: *"This
position is linked to 12 documents and 4 users — deactivating it will hide
position-restricted documents from users in this position."* Documents and
user assignments are **not** removed; the position just stops appearing as
an active option going forward.

### External Postgres tab (Text-to-SQL)

Lets you register a **read-only** external Postgres database so operators
can ask analytical questions in chat that get answered by live SQL queries
(`src/spark/services/agentic/query_database.py`) instead of document
retrieval. This is the admin side of
[Scope §P-05](./DELIVERY_ACCEPTANCE.md) — it only becomes useful once you
finish this setup.

1. **Register a connection**: name, host, port, database, username,
   password, SSL mode (`prefer` / `require` / `disable`), optionally a
   single owning factory (blank = visible to every factory that can use
   this source), and an optional `scope_column` (e.g. `factory_id`) if the
   remote tables need row-level factory filtering.
2. **Test connection** — you can test the raw form values *before* saving
   (`POST /admin/data-sources/test`), and again per-saved-source afterward
   (`POST /admin/data-sources/{id}/test`).
3. **Discover tables** (`GET /admin/data-sources/{id}/discover`) —
   introspects the remote schema and lists tables with column metadata. A
   successful connection test auto-triggers discovery so you don't need a
   second click.
4. **Allow-list tables**: check the tables you want queryable. For each
   checked table you can further scope it to specific factories and/or job
   positions (empty = accessible to everyone who can reach this data
   source at all). Nothing is queryable in chat until you **save** the
   selection.
5. **Enable in chat** — a separate checkbox (`is_enabled`) on the source
   card; you can register and configure a source without turning it on yet.
6. **Delete** — removes the data source and its table allow-list entirely
   (confirmation dialog; irreversible).

The stored password is encrypted at rest via `secret_box`
(`src/spark/core/secret_box.py`), keyed by `DATA_SOURCE_ENCRYPTION_KEY`.
Rotating that key requires re-encrypting existing data-source credentials —
see the credential-rotation guidance in
[`docs/DELIVERY_ACCEPTANCE.md` §10](./DELIVERY_ACCEPTANCE.md).

### API keys tab

Issues **bearer tokens for machine/service integrations** — not for human
login. A key always acts with the roles and factory access of whatever
**user account** it's bound to, so the recommended pattern (stated directly
in the UI) is: create a dedicated service-account user in the Users tab
first, grant it only the access it needs, then issue a key against that
account rather than against a real person's account.

| Field | Notes |
| --- | --- |
| Name | Human-readable label for what/who uses it, e.g. `partner-x-website` |
| Account | Which user the key authenticates as |
| Expiry | Optional date; blank = never expires |

The full key is shown **once**, in a modal, immediately after creation —
only its hash is stored server-side, so if it's lost you must issue a new
one. Use it as `Authorization: Bearer <key>` from a server, never embedded
in frontend code.

Two distinct destructive actions, both irreversible:

- **Revoke** — flips `is_active` to `false` and records `revoked_at`. The
  key row stays visible in the list (for audit history) but stops working
  immediately.
- **Delete** — removes the row entirely.

Both bust the API-key auth cache (`bust_api_key_cache`) so the change takes
effect on the very next request, not after a TTL.

## Factory management: `/admin/factories`

A separate page (not a tab under `/admin`) with its own admin check.

**Create a factory**: a `factory_id` (2–19 characters: letters, digits, `-`,
`_` — the form auto-uppercases what you type, e.g. `f-03` → `F-03`), a
display name, and an optional location. Creating a factory also
best-effort provisions its Qdrant collections in the background
(`_ensure_qdrant_for_factory`) — a failure there is logged as a warning and
does not block factory creation, but it means retrieval for that factory
may not work until the collection exists (re-run
**"Sync Qdrant"** from the [Control Room](#system-admin--control-room-system-admin)
if you suspect this happened).

**Per-factory settings** — click "Settings" on a factory row to expand an
inline form:

| Setting | Effect |
| --- | --- |
| RAG `top_k` (1–20) | How many chunks are retrieved before fusion/rerank for this factory |
| RAG `min_max_score` | Score floor below which retrieval is treated as "no evidence" (blank = system default) |
| Ingest backend | Fixed to `native` — shown disabled in the UI; native ingestion is the only supported production path (`docker-compose`/RAGFlow paths are deprecated, see [03 — Known Limitations](./DELIVERY_ACCEPTANCE.md)) |
| Chunking strategy | `recursive` or `semantic` |
| Timezone | Defaults to `Asia/Bangkok` |
| Predictive backend | `heuristic` / `mcp` / `hybrid` — **this setting has no working backend to configure.** Predictive maintenance / DeepAnalyze integration is out of scope for this delivery (only `.pyc` remnants remain in `src/spark/integrations/`, see [03 — Known Limitations](./DELIVERY_ACCEPTANCE.md)); changing this value has no observable effect today |
| Notifications | Enable/disable outbound webhook notifications (ingest failures, "hot" insights) and set the webhook URL |

A small "effective settings" summary line under the form shows the
resolved values actually in use (falling back to system defaults for
anything unset), separate from what's explicitly stored for the factory.

**Delete a factory** — **super admin only** (see
[Super admin](#super-admin-is_super_admin) above). The confirmation dialog
states the real constraint: the factory must have no documents, machines,
feedback, or QA cache entries left, or the delete call fails with a 409.
There is no cascading "wipe everything in this factory" button — clean up
the dependent data first.

## Document release (quarantine review)

Not on an admin page — it lives inline on the **Documents** page
(`web/components/documents/ReleaseDocumentButton.tsx`), as a small amber
"pending review" pill on any document the content-safety scanner
quarantined during ingestion (`ingest_status: quarantined` or
`pending_release`).

Clicking it opens a modal showing the **content risk score** and the
specific **policy findings** that triggered quarantine (rule ID, severity,
matched text snippet). From there:

- **Release (approve)** — calls `POST /documents/{id}/release`, which
  re-queues the document for indexing from its stored quarantine artifact
  and flips its status to `indexing`.
- Close the modal to leave it quarantined for now.

Two enforcement rules to know about, both server-side:

1. **Separation of duties**: the person who uploaded a document cannot
   release their own upload unless they're an admin — `document_release.py`
   explicitly checks `doc.created_by == p.user_id and not p.is_admin` and
   returns 403. A second reviewer (or an admin) has to do it.
2. **Permission mismatch to be aware of**: the release *button* is shown to
   anyone with write access to that factory (`canWriteFactory`), but the
   release *endpoint* additionally requires the `release_documents` role or
   admin (see [Roles & permissions](#release_documents-role--exists-in-code-not-exposed-in-the-ui)).
   Since that role isn't assignable from the UI today, a non-admin
   write-access user can see and click the button but will get a 403 from
   the API. In practice, treat document release as an **admin-only**
   action until `release_documents` is exposed in the Users tab.

## Feedback triage: `/feedback`

Accessible to anyone with write access to a factory (not admin-only) — it's
where operators report a wrong or incomplete chat answer, and where those
reports get worked. The page renders `FeedbackInboxPanel`, scoped to the
currently selected factory.

**Status lifecycle** (`src/spark/services/feedback_service.py`):

```
open → triaged → resolved
              ↘  wont_fix
```

`resolved` and `wont_fix` are terminal. Updating a feedback item
(`PATCH /feedback/{id}`) accepts a new `status` and/or a free-text
`resolution_note`.

Each feedback item can carry: the chat session/message it came from (if
submitted from chat), a linked document + page (if submitted from the
document viewer), a machine ID, an `issue_type`, free-text comment, and up
to several photo attachments (served back through
`GET /feedback/{id}/attachments/{sort_order}`, streamed from object
storage — not embedded as base64).

## System Admin / Control Room: `/system-admin`

A dense, single-screen "NOC" (network operations center) style dashboard —
branded in the UI footer as **"Neo Control Room · Cyber NOC"** — for admins
to see system health at a glance and take a handful of operational actions.
Gated by `SuperAdminGuard`, but despite the name it allows **any admin**,
not only super admins (`allowed = isAdminUser() || profile.roles.includes("admin") || profile.is_super_admin`).

It calls a single endpoint, `GET /api/v1/system-admin/dashboard`, which
fans out ~17 independent data-gathering calls in parallel
(`asyncio.gather(..., return_exceptions=True)` in `system_admin_service.py`)
so one failing subsystem (e.g. Prometheus being off) degrades that one
panel instead of breaking the whole dashboard.

### Dashboard panels

| Panel | Shows |
| --- | --- |
| Token Usage | LLM prompt + completion token counts, last 7 days |
| Active Users | Distinct users active in a rolling 15-minute window, plus a 7-day trend |
| Messages | Chat message volume, last 7 days |
| Sessions | Chat sessions created, last 7 days |
| Ingest Jobs | Ingestion job counts/outcomes, last 7 days |
| Connectivity | Live up/down check per dependency (Postgres, Redis, Qdrant, storage, LLM gateway, …), shown as an "X/Y OK" count |
| Latency p95 | 24h p95 latency — requires the optional Prometheus/Grafana overlay; shows "Prometheus off" otherwise ([03 — Known Limitations, §P-08](./DELIVERY_ACCEPTANCE.md)) |
| Infrastructure | Qdrant/Postgres infra signals, including a "chunk drift" alert if vector counts and Postgres chunk counts disagree |
| AI & RAG | Agentic and RAG **circuit breaker** state — flags red if either circuit is open |
| PostgreSQL | Connection pool / table-level stats |
| Ingest Status | Donut chart of documents by ingest status (indexed, pending, quarantined, failed, …) |
| Debug | Quick links to open dependency consoles (e.g. Grafana) in a new tab |

A derived **incident feed** (`_build_incidents`) surfaces the same
signals as a flat list of warnings/criticals — e.g. a downed dependency,
maintenance mode being on, an open circuit breaker, or a nonzero count of
failed ingest jobs in the last 7 days — so you don't have to scan every
panel to notice something is wrong.

### Actions bar

Five buttons, each calling `POST /api/v1/system-admin/actions/{action}`:

| Button | Action | What it actually does |
| --- | --- | --- |
| ล้างแคช (Clear cache) | `clear-cache` | Flushes all `spark:`-prefixed Redis cache keys and the in-process `/readyz` cache |
| ซิงก์ Qdrant (Sync Qdrant) | `qdrant-sync` | Enqueues `reconcile_vectors_task(factory_id=None, auto_fix=True)` — a background Celery job that reconciles Postgres chunk records against Qdrant vectors across all factories |
| เปิด/ปิดบำรุงรักษา (Toggle maintenance) | `maintenance-on` / `maintenance-off` | Puts the app in maintenance mode with an optional custom message shown to users (the text field next to the buttons) |
| รีเซ็ต Agentic (Reset agentic) | `reset-agentic` | **Currently a no-op** — the handler just returns `{"note": "agentic path disabled"}`. The button exists for a circuit that isn't wired up in this delivery; don't rely on it doing anything |
| รีเซ็ต RAG (Reset RAG) | `reset-rag` | Manually closes the RAG circuit breaker if it's open, logging the operator's username as the reason |

"Clear cache" and "Toggle maintenance" are styled as the two "danger"
actions in the UI (they visibly affect users immediately); the other three
are lower-risk.

## Audit exports

Two **separate** exports exist — don't confuse them:

| | `GET /api/v1/admin/audit/export` | `GET /api/v1/audit/export` |
| --- | --- | --- |
| Who can call it | `admin` role | `compliance_officer` role, or admin |
| Format | CSV download | JSON bundle |
| Scope | All factories (no `factory_id` filter) | Requires `factory_id` unless caller is admin/compliance officer; can filter by `classification_level` |
| Content | Retrieval log only, `days` param (1–365, default 90) | Retrieval log **and** the WORM (write-once-read-many) audit chain, with `chain_valid` integrity confirmation, redacted rows, and a signed, time-limited download token |
| Purpose | Quick operational CSV pull | Formal compliance bundle for audits — this is the one referenced by the delivery package's audit-export capability |

## Permission reference

Quick lookup of the guard on each admin-relevant endpoint group
(`src/spark/core/security.py` primitives):

| Area | Guard | Effective requirement |
| --- | --- | --- |
| Users, job positions, factories (CRUD), API keys, data sources, system-admin dashboard/actions | `require_role("admin")` | `admin` role or `is_super_admin` |
| Delete factory | `require_super_admin()` | `is_super_admin` only |
| Release a document | `enforce_release_documents` | admin, or `release_documents` role (not assignable via UI today) |
| Feedback list (factory-scoped) / update | `enforce_factory_access(..., "write")` | write-level factory access, `operator`, or admin |
| Compliance audit export | `enforce_compliance_export` | admin, or `compliance_officer` role |
| Admin CSV audit export | `require_role("admin")` | `admin` role or `is_super_admin` |

## Common admin recipes

**Onboard a new factory employee with read-only chat access**
1. `/admin` → Users tab → Add user.
2. Role: `employee`. Set factory access to `read` for their factory(ies).
3. Optionally assign job positions if some documents should be restricted
   to their role.
4. Hand them the one-time temporary password shown in the modal; they sign
   in at `/login` and should change it afterward (Account page).

**Let someone upload documents and give feedback (not just read)**
- Either set their role to `operator` (gets write everywhere they have any
  access), or keep them `employee` and explicitly grant `write` on the
  specific factories they need — see
  [Factory access levels](#factory-access-levels) for the difference.

**Add a new factory and get it usable end-to-end**
1. `/admin/factories` → create the factory (ID, name, location).
2. Confirm Qdrant collections came up; if in doubt, run **Sync Qdrant**
   from `/system-admin`.
3. Grant relevant users factory access from `/admin` → Users tab.
4. Adjust per-factory RAG/ingest/notification settings if the defaults
   don't fit (`/admin/factories` → Settings).

**Connect an external database for Text-to-SQL**
1. `/admin` → External Postgres tab → fill in connection details.
2. Test connection → Discover tables → check the tables to expose → scope
   each to the right factories/positions → Save.
3. Flip "Enable in chat" once you're satisfied with the allow-list.

**Issue an API key for a partner integration**
1. Create a dedicated service-account user first (Users tab), with only
   the factory access/role that integration actually needs.
2. API keys tab → issue a key against that account, with an expiry if the
   integration is time-boxed.
3. Copy the key immediately — it will not be shown again. Revoke (not
   delete) it if you need to disable it but keep the audit row.

**Grant `is_super_admin` (no UI for this yet)**
As an existing super admin, call the API directly:
```bash
curl -X PATCH "$API_BASE/api/v1/admin/users/$USER_ID" \
  -H "Authorization: Bearer $YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_super_admin": true}'
```
The target user's session is invalidated immediately, same as any other
admin update.

**Release a quarantined document**
1. On `/documents`, find the amber "pending review" pill.
2. Open it, read the policy findings and risk score.
3. If it's a false positive or acceptable, click "Release (approve)" — as
   a **different admin than whoever uploaded it**, per the
   separation-of-duties rule.

## Gotchas and non-obvious behavior

- **Any admin change ends the target user's session.** Warn users before
  bulk role/access changes if they're mid-task.
- **`is_super_admin` has no UI toggle** — API only, and only another super
  admin can grant it.
- **The "Predictive backend" factory setting does nothing observable** —
  the feature it configures isn't part of this delivery.
- **The document-release button can appear for users who will get a 403**
  — the UI check (`canWriteFactory`) is broader than the API's actual
  requirement (`release_documents` role or admin). Don't be surprised if a
  non-admin write user reports the button "doesn't work."
- **"Reset Agentic" in the Control Room does nothing** — it's a disabled
  no-op, unlike "Reset RAG" which is real.
- **Job positions can only be deactivated, never deleted** — plan position
  codes accordingly; you can't reclaim a slug once used, only retire it.
- **Deleting a factory requires it to be empty first** (no docs, machines,
  feedback, or QA cache) — there's no cascading delete.
- **Demo mode (`AUTH_REQUIRED=false`) makes every request a super admin.**
  Never enable it outside a disconnected local/demo environment.

## Related docs

- [docs/DELIVERY_ACCEPTANCE.md](./DELIVERY_ACCEPTANCE.md) — scope, known
  limitations, and what's out of scope (Insights/Predictive/DeepAnalyze,
  etc.)
- [docs/HANDOVER.md](./HANDOVER.md) — full engineering handover
- [docs/user-guide.md](./user-guide.md) — the non-admin operator guide
- [docs/api-overview.md](./api-overview.md) — API route map
