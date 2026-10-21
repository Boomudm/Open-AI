# Neo Chat — Delivery & Acceptance Package

> **Document ID:** NEOCHAT-DELIVERY-2026-001 · **Version:** 1.0 (delivery edition)
> **Classification:** Confidential — internal to the parties named below. Do not distribute outside the
> organization without written permission from the document owner.
> **System reference:** Neo Chat **v1.0.0**, git tag `v1.0.0`, commit `b9c9436` (branch `main`)
> **Prepared:** 2026-07-20 · **Planned delivery date:** 2026-07-22
>
> This document is the **commercial and acceptance counterpart** to
> [`docs/HANDOVER.md`](./HANDOVER.md). `HANDOVER.md` explains **what the system is and how it works**
> (architecture, code map, operations, runbooks). This document defines **what "delivered" means, how
> acceptance is measured, what is and is not covered by warranty, and what happens after sign-off.** Read
> both; where they overlap, the more specific statement in whichever document addresses the topic
> controls.

---

## Table of contents

0. [About this document](#0-about-this-document)
1. [Parties](#1-parties)
2. [Executive summary](#2-executive-summary)
3. [Delivery baseline](#3-delivery-baseline)
4. [Scope of delivery](#4-scope-of-delivery)
5. [Quality evidence and acceptance tests](#5-quality-evidence-and-acceptance-tests)
6. [Acceptance procedure and timelines](#6-acceptance-procedure-and-timelines)
7. [Warranty and support](#7-warranty-and-support)
8. [Exclusions and limitation of liability](#8-exclusions-and-limitation-of-liability)
9. [Known limitations and disclosed carve-outs](#9-known-limitations-and-disclosed-carve-outs)
10. [Confidential credential hand-off](#10-confidential-credential-hand-off)
11. [Acceptance certificate](#11-acceptance-certificate)
12. [Definitions](#12-definitions)
13. [Document history](#13-document-history)

---

## 0. About this document

### 0.1 Purpose

This package exists to:

1. Fix, in writing, exactly what is delivered, partially delivered, and out of scope for Neo Chat
   v1.0.0 — so scope cannot be argued after the fact.
2. Give the accepting party an **objective, repeatable** basis for acceptance (test commands and pass
   criteria — not a subjective satisfaction standard).
3. Disclose known limitations and dead/orphaned code **before** acceptance, so both parties treat them as
   acknowledged facts rather than defects discovered later.
4. Set warranty, support, liability, and confidentiality terms for the hand-off.
5. Serve as the reference for any post-delivery discussion about what was and wasn't promised.

### 0.2 Relationship to other documents — order of precedence

When documents disagree, resolve the conflict in this order:

1. **A signed business contract or work order between the parties**, if one exists and speaks to the
   point directly.
2. **The actual software at the reference point** — git tag `v1.0.0`, commit `b9c9436`, branch `main`,
   with its configuration.
3. **This document** (`docs/DELIVERY_ACCEPTANCE.md`), together with `docs/HANDOVER.md` for technical
   detail — these are the delivery record.
4. Everything else: `README.md`, `CHANGELOG.md`, other files under `docs/`, in-app copy, or the
   marketing/landing page. These are useful context but are **not binding commitments** on their own,
   and where they conflict with the actual software or with this document, the software and this
   document control.

### 0.3 Employment-handover context

This delivery is a **work-product hand-off between an employee and their employer**, not a sale by an
external vendor:

- The delivering party produced Neo Chat while employed as a Backend / AI Developer at the CPF Center of
  Engineering Excellence — Repair and Development Center for Prepared Food Machinery Engineering
  ("the Center").
- The accepting party (the Center) and the delivering party belong to the **same organization**.
- Compensation for this work is already included in the delivering party's salary. **There is no
  separate fee, purchase price, or invoice for this delivery.**
- "Client" or "ผู้ว่าจ้าง" wherever it appears in this document set means the Center / accepting
  organization, in this employment context — not a third-party commercial customer.
- Copyright in the work product vests in the organization per [`LICENSE`](../LICENSE) and applicable
  employment law; the delivering party does not assert a commercial ownership claim over the delivered
  system. This fact is exactly why the liability terms in [§8](#8-exclusions-and-limitation-of-liability)
  are scoped to an employment relationship rather than a vendor contract with a dollar-value cap.

### 0.4 Confidentiality and distribution

1. This document, and any appendix or hand-off form attached to it, is **confidential** between the
   parties.
2. Do not forward outside the organization without written permission from the document owner.
3. **Do not paste secret values (passwords, API keys, tokens) into this document, into any copy of it, or
   into any ticket that references it.** Section 10 explains how credentials move instead.
4. The accepting party is responsible for access control over its own copies of this document.

### 0.5 Document control

| Field | Value |
|---|---|
| Document name | Neo Chat — Delivery & Acceptance Package |
| Document ID | NEOCHAT-DELIVERY-2026-001 |
| Document version | 1.0 (delivery edition) |
| System version delivered | 1.0.0 |
| Software reference point | git tag `v1.0.0` / commit `b9c9436` (branch `main`) |
| Language | English (this file); a Thai narrative reference exists as the internal working draft this file was adapted from |
| Classification | Confidential — parties only |
| Status | Delivery / acceptance edition |
| Storage | This repository, `docs/DELIVERY_ACCEPTANCE.md` |

---

## 1. Parties

### 1.1 Delivering party

| Field | Detail |
|---|---|
| Name | Narinthon Yangngam (นรินธร ยางงาม) |
| Role | Backend / AI Developer |
| Organization | CPF Center of Engineering Excellence — Repair and Development Center for Prepared Food Machinery Engineering |
| Role in this delivery | Developer and deliverer of Neo Chat |
| Contact | tedd0781@gmail.com |
| Scope of responsibility | Deliver the software, its test suite, this delivery package, and usage/acceptance guidance within the scope stated in this document |

### 1.2 Accepting party / Client

| Field | Detail |
|---|---|
| Organization / site | CPF Center of Engineering Excellence (Nong Chok, Bangkok) |
| Owning unit | Repair and Development Center for Prepared Food Machinery Engineering |
| Authorized signatory | _to be completed before sign-off_ |
| Title | _to be completed before sign-off_ |

### 1.3 Other stakeholders (as applicable)

| Role | Party | Note |
|---|---|---|
| Infrastructure / network owner | Accepting party | Owns servers, network, domain, TLS |
| LLM gateway / model quota owner | Accepting party | External dependency of the system — see [§9](#9-known-limitations-and-disclosed-carve-outs) |
| Factory document data owner | Accepting party | Responsible for the quality of documents ingested |

---

## 2. Executive summary

| Topic | Summary |
|---|---|
| System delivered | Neo Chat — an on-prem, document-grounded Q&A assistant (RAG: Retrieval-Augmented Generation) for factory knowledge |
| Business purpose | Let factory staff search and ask questions against internal documents with source citations, scoped by factory/role |
| Delivery status | Ready for acceptance within the scope defined in [§4](#4-scope-of-delivery), backed by an objective test suite ([§5](#5-quality-evidence-and-acceptance-tests)) |
| Software reference point | v1.0.0 @ `b9c9436` (branch `main`) |
| What the accepting party must provide | LLM gateway access / model quota, infrastructure, network/domain/TLS, and the real factory documents to ingest |
| Key risks both parties should acknowledge | The system depends on an external LLM gateway; AI answers are a decision-support tool, not a final verdict; some UI/config traces exist for features with no working backend (out of scope) |
| Documents to read together | [§4](#4-scope-of-delivery) (scope) · [§5](#5-quality-evidence-and-acceptance-tests) (acceptance tests) · [§9](#9-known-limitations-and-disclosed-carve-outs) (limitations) · [§11](#11-acceptance-certificate) (sign-off) |

**What Neo Chat is.** Neo Chat is an internal, on-prem/private-deployment system that lets users ask
questions in Thai about factory documents and knowledge, and receive answers with source citations. The
system retrieves from an ingested document store before synthesizing an answer through a language model.
It is not a generic chat product; it is built from four layers:

1. **Knowledge Q&A (RAG)** — hybrid retrieval (dense / sparse / lexical), fusion, reranking, and
   grounded answer generation.
2. **Document ingestion** — multi-format document support with a trust/quality pipeline before
   publication.
3. **Access and security** — authentication, factory/role-scoped authorization, and misuse guardrails.
4. **Administration** — admin and system-admin surfaces for users, factories, data sources, and health.

**Naming note.** The delivered product name is **Neo Chat**. "NeoSpark," which appears in some
deployment hostnames/config (e.g. `neospark.kcalsion.com`), is a deployment/domain label, not a separate
product.

**Value delivered:**

| Dimension | What the accepting party actually gets |
|---|---|
| Knowledge access | Staff can query factory documents without manually searching files, with citations back to source |
| Organizational control | Multi-factory separation and role-based access reduce accidental cross-unit data exposure |
| Answer quality | Grounding, evidence-consistency checks, Thai-language enforcement, and fail-closed behavior when evidence is weak |
| Ingestion | A pipeline with 13 document-type profiles and a trust/policy/quality gate before publication |
| Acceptance readiness | A large, real test suite (278 pytest files) and an acceptance procedure tied to §5 and §6 |
| Ongoing operability | A system-admin surface for core component health and basic maintenance actions |

**What the accepting party must supply** for the system to work in production: infrastructure and GPU
(if used), network/domain/TLS, an LLM gateway with quota, the real factory documents, user/role/factory
account data, and — only if Text-to-SQL is wanted — an external analytics database. See
[§4.3](#43-partially-delivered--conditions-to-reach-full-operation)
and [§9](#9-known-limitations-and-disclosed-carve-outs) for the exact conditions attached to each.

---

## 3. Delivery baseline

| Item | Value at this delivery |
|---|---|
| Product / version | Neo Chat 1.0.0 |
| Git tag | `v1.0.0` |
| Git commit | `b9c9436` |
| Reference branch | `main` |
| Evidence used to confirm capability | Source code (`src/`, `web/`), configuration (`configs/`), container/compose files (`docker-compose*.yml`, `Dockerfile*`), install/operations scripts (`deploy/`, `scripts/`), and the test suite (`tests/`, `web/e2e/`) |
| Planned delivery date | 2026-07-22 |

**Controlling principle:** if any other document in this repository — `README.md`, `CHANGELOG.md`, or
any other `.md` file — conflicts with the actual delivered software at this reference point, **the real
software controls**. If the software changes after this reference point, those changes are not covered
by this delivery's acceptance, warranty, or scope statements unless the parties agree to that in writing
separately (a change request).

---

## 4. Scope of delivery

Scope is split into three tiers so nothing is assumed to be delivered just because a button, an
environment variable, or a doc file mentions it.

| Tier | Meaning | Examples |
|---|---|---|
| **Delivered** | Exists in the real system and is acceptance-testable | Chat/RAG, document ingestion, user/factory management, machines, feedback, system-admin, the test suite |
| **Partially delivered** | Exists and works, but full operation depends on something the accepting party must supply or configure | Browser-based voice input, any LLM/vision-dependent output, Text-to-SQL (needs an external database) |
| **Out of scope** | Not delivered, or has no working backend/source behind it | Insights/Predictive dashboards with no API, DeepAnalyze integration (no source), server-side speech-to-text (Whisper) |

**Scope principles** (apply throughout this document):

1. Something only counts as delivered if it exists in the software at the reference point and can be
   demonstrated from an endpoint, screen, config, or test — not from a doc file or a landing-page claim
   alone.
2. A feature mentioned only in a button label, an `.env.example` key, or old documentation, without a
   working backend, is **not** a delivered capability.
3. A capability that depends on an external dependency (LLM gateway, model quota, network, a client
   database) is delivered as *software*, but its real-world availability is not guaranteed — see §4.3
   and §9.
4. Demonstrations, training, environment troubleshooting, and post-delivery requests do not, by
   themselves, expand scope.
5. Disclosed limitations (§9) and out-of-scope items (§4.4) are **not defects**.

### 4.1 Delivered — capability groups

| Group | Summary | Representative evidence |
|---|---|---|
| A. API platform & UI | API v1 under `/api/v1` across 19 router modules; Next.js web app across 14 pages (`login`, `signup`, `auth/callback`, `chat`, `documents`, `upload`, `machines`, `feedback`, `admin`, `admin/factories`, `system-admin`, `account`, `privacy`, home); health/readiness/metrics endpoints | `src/spark/api/v1/router.py`, `web/app/**/page.tsx` |
| B. Knowledge Q&A (RAG / Chat) | Hybrid retrieval (dense + sparse + lexical), fusion + rerank, grounded answers with citations, confidence tiers, fail-closed/degrade behavior | `src/spark/retrieval/`, `src/spark/generation/` |
| C. Agentic tools & external data (software layer) | Document-search tool calling and read-only Text-to-SQL routing exist in software; real use requires the client's data source per §4.3 | `src/spark/services/chat_orchestrator.py` |
| D. Document ingestion | 13 document-type profiles, preflight, staged pipeline (parse / trust / transform / index / finalize), quarantine and release | `configs/ingestion/` (13 files), `src/spark/ingestion/` |
| E. Security, authentication, authorization | JWT, password login, Google OAuth, RBAC, factory-scoped ACL, API keys, production lock | `src/spark/core/security.py` |
| F. User & admin features | Account, admin (users/positions/document access/feedback triage), factory admin, machine registry, system-admin | `web/app/admin/`, `web/app/system-admin/` |
| G. Data, infrastructure, background work | Compose/Dockerfiles (9 compose files), Celery workers + beat, PostgreSQL, Redis, Qdrant, MinIO, 58 Alembic migrations | `docker-compose*.yml`, `alembic/versions/` |
| H. Quality and test suite | 278 pytest files, `tests/contracts/` gate, 3 Playwright e2e specs, 5 web unit test files, CI workflow | `tests/`, `web/e2e/`, `.github/workflows/ci.yml` |

### 4.2 Deliverables register (concrete items handed over)

| Code | Item | Form / evidence | Status |
|---|---|---|---|
| DEL-01 | Full source code at the reference point | Git tag `v1.0.0` @ `b9c9436` — `src/`, `web/`, and related repo components | Delivered |
| DEL-02 | Container/runtime definitions | 9 `docker-compose*.yml` files + `Dockerfile.api` / `Dockerfile.web` / `Dockerfile.worker` | Delivered |
| DEL-03 | System configuration | `configs/` — 13 ingestion profiles, 16 LLM profiles, retrieval/generation/chunking/compliance/eval config | Delivered |
| DEL-04 | Database schema & migrations | 58 Alembic migrations + ORM models under `src/spark/db/models/` | Delivered |
| DEL-05 | GPU sidecar (optional accelerator) | `gpu-sidecar/` | Delivered (optional) |
| DEL-06 | Operations / install / ops scripts | `scripts/`, `deploy/`, `ops/` | Delivered |
| DEL-07 | Test suite and eval configs | 278 pytest files, `web/e2e/` (3 specs), web unit tests (5 files), `configs/eval/`, `scripts/test.sh` | Delivered |
| DEL-08 | This delivery package | `docs/DELIVERY_ACCEPTANCE.md` + `docs/HANDOVER.md` | Delivered |
| DEL-09 | Sample documents for demonstration | Sample manuals/diagrams used to demo the ingest→chat path, if the accepting party chooses to receive them | Delivered as a companion (optional) |
| DEL-10 | Credentials / secrets | **Not included in this document** — transferred through a separate secure channel per [§10](#10-confidential-credential-hand-off) | Transferred separately |

Note on DEL-09: any vendor-authored sample manuals used for demo purposes may carry third-party
copyright. Use beyond demonstration/acceptance purposes is the accepting party's responsibility; do not
redistribute publicly without permission.

### 4.3 Partially delivered — conditions to reach full operation

| Code | Item | Condition for full operation | Not covered by this delivery |
|---|---|---|---|
| P-01 | Voice input (browser speech-to-text) | Works only through the browser's Web Speech API | No server-side transcription (Whisper) is included |
| P-02 | LLM gateway / generation from an external model | Requires a working, funded gateway the accepting party supplies | Gateway uptime, latency, and cost |
| P-03 | Vision extraction for drawing-type documents | Requires a vision-capable model profile and quota | Extraction quality when the gateway/model is degraded |
| P-04 | GPU sidecar (embed/rerank acceleration) | Requires GPU hardware | Not required at every site — CPU fallback applies |
| P-05 | Text-to-SQL / external data analytics | Requires an admin-registered external Postgres data source with read access | The client's database itself |
| P-06 | UI language (partial i18n) | Landing page has Thai/English; the main app UI is Thai | Full in-app translation of the whole product |
| P-07 | Demo mode (`AUTH_REQUIRED=false`) | Intended for demos only | Must be turned off before any real/open-network use — see §9, L-08 |
| P-08 | Optional observability overlay (Prometheus/Grafana) | Requires enabling the observability compose overlay | Not enabled by default at every site |

### 4.4 Out of scope

| Code | Item | Why it's out of scope |
|---|---|---|
| X-01 | Insights / Analytics / Inventory / Predictive dashboards (product-facing) | Frontend client/components exist; no API router serves them |
| X-02 | Predictive maintenance / DeepAnalyze integration | Only compiled `.pyc` artifacts remain; no source |
| X-03 | Server-side transcription (Whisper / transcribe API) | Client references the endpoint; it does not exist in the delivered API |
| X-04 | Legacy product dashboard page | Current `web/app/` has no dashboard as a primary surface (`/system-admin` is a separate, in-scope surface) |
| X-05 | `Component` / `ComponentAlias` entities | Database models exist; no product-level surface/API ships them |

Also out of scope, regardless of any trace left in the repository: infrastructure and network the
accepting party owns; LLM gateway procurement and quota; the accepting party's real factory documents;
24/7 SLA or on-call service; and anything requiring a signed change request. Landing-page copy,
`.env.example` keys with no real consumer, `.pyc` remnants with no source, and deployment hostnames
(e.g. "NeoSpark") never create scope on their own.

---

## 5. Quality evidence and acceptance tests

Acceptance is evidence-based, not a subjective satisfaction standard. The formal, mandatory acceptance
tests are **AT-01 through AT-05**. All commands below are verified runnable against this reference point.

| ID | Suite | Command | Pass criteria |
|---|---|---|---|
| AT-01 | Backend suite (excluding chaos) | `bash scripts/test.sh` | Completes successfully |
| AT-02 | Contract gate | `uv run pytest tests/contracts/ -q` | 100% pass (20 contract test files at this reference point) |
| AT-03 | Web end-to-end | `cd web && npx playwright test` | All 3 specs pass (`smoke`, `handover-flow`, `admin-api-keys`) |
| AT-04 | Web unit tests | `cd web && npm test` | All 5 unit test files pass |
| AT-05 | CI parity | ruff lint, pytest (excluding chaos) with ≥ 60% coverage, and `web` typecheck/lint/test/build | Matches the `.github/workflows/ci.yml` `python` and `web` jobs |

**Supplementary, non-blocking evidence** (useful, but not required for acceptance): nightly/chaos suites,
CodeQL, and `golden_real_docs` eval against a live GPU + live LLM gateway. These may be deferred when the
required infrastructure or gateway isn't available at acceptance time, without blocking AT-01–AT-05.

**Scale at this reference point:** 278 backend pytest files; 3 Playwright e2e specs; 5 web unit test
files; 13 ingestion profiles and 16 LLM profiles under `configs/`. These are point-in-time facts, verified
against the `main` branch at the time this document was written — re-verify before relying on them if
time has passed.

---

## 6. Acceptance procedure and timelines

### 6.1 Definitions used in this section

| Term | Meaning |
|---|---|
| Ready-for-review date | The date the delivering party notifies, in writing, that the deliverables in §4.2 are ready to be reviewed against this section |
| Review window | The period the accepting party has to review and, if applicable, reject in writing, starting from the ready-for-review date |
| Defect | The system behaves differently from the delivered behavior within the §4 scope, on a suitable test environment, per this document |
| Carve-out | An item disclosed in §4.3/§4.4/§9 — not a defect, and not grounds to refuse acceptance on its own |
| Deemed acceptance | The system is treated as fully accepted once the conditions below are met, even without a signature on §11 |
| Deemed use | The accepting party is treated as having accepted whatever part of the system it puts into real/production use |

### 6.2 Prerequisites before review starts

| Item | Detail |
|---|---|
| Software reference | `v1.0.0` / `b9c9436`, or a build both parties confirm is equivalent |
| Deliverables present | DEL-01 through DEL-08 accessible (DEL-05/DEL-09 as agreed; DEL-10 via §10) |
| Test environment | Equivalent to what the delivered scripts expect (e.g. `scripts/test.sh`); tests are not run against a production database |
| Reviewers | A representative of each party jointly runs and records the AT-* results |
| External dependencies | If a gateway-dependent path will be demonstrated live, the accepting party must have gateway/quota ready — its absence does not delay the mandatory AT criteria |

If a prerequisite is missing on the accepting party's side, record it as "not yet ready for review" and
extend the ready-for-review date accordingly — this is not automatically treated as a software delay.

### 6.3 Pass criteria (mandatory)

Acceptance is considered to **pass** when all of the following hold:

1. AT-01 through AT-05 pass on a suitable environment.
2. No open, valid, blocking defect remains within the §4 scope after one remediation cycle (§6.6).
3. No valid written rejection is received within the review window, or the deemed-acceptance/deemed-use
   conditions below are met.

### 6.4 Review window, deemed acceptance, deemed use

| Item | Value |
|---|---|
| Review window | **3 business days** from the ready-for-review date (Thai business calendar, unless the parties agree otherwise in writing) |
| Valid rejection | Must be in writing, within the window, and must state: (a) the AT code or a reproducible procedure; (b) the environment used; (c) the actual result; (d) why it falls within the §4.1 scope |
| Invalid rejection | Citing general dissatisfaction, an out-of-scope item (§4.4), a limitation (§9), gateway unavailability, a new/untested case outside AT-*, or a non-reproducible claim — none of these extend the window or block acceptance |

**Deemed acceptance** applies — the system is treated as fully accepted within its delivered scope —
when any of the following occurs:

1. The review window elapses with no valid written rejection, or
2. The accepting party states in writing that it accepts, or
3. Both parties sign §11 as accepted or conditionally accepted.

**Deemed use** applies if the accepting party puts the system into real or production use (including
opening it to end users for regular use): the part put into use is treated as accepted, even without a
§11 signature — without prejudice to any valid defect already reported within the review window before
that use began.

**Partial acceptance:** a deliverable or capability that already passes its criteria is accepted
separately; a gateway-dependent capability may be accepted at the software layer while live-model proof
is deferred; out-of-scope items never become a condition blocking acceptance of what has already been
delivered.

### 6.5 Defect vs. carve-out

**Treated as a defect:** AT-01–AT-05 failing on a correctly prepared environment; or in-scope (§4.1)
behavior reproducibly differing from delivered behavior, for reasons other than an external factor.

**Not treated as a defect (carve-out):**

| Category | Example |
|---|---|
| Environment / misuse | Running tests with `APP_ENV=production`, missing Postgres/Redis, running tests against a production DB |
| External services | LLM gateway outage, quota exhaustion, slow network, the accepting party's DNS/TLS |
| Out of scope / dead code | Insights, Predictive/DeepAnalyze, Whisper server, legacy dashboard — per §4.4 and §9 |
| Partially delivered with unmet conditions | Text-to-SQL with no external DB configured; browser voice input on an unsupported browser |
| New requirements | Requesting a feature or test case outside AT-* after delivery |
| AI answer business quality | An answer that doesn't match business expectations even though the system cited the available documents correctly, or the source document itself was low quality |
| Supplementary suites | chaos / nightly / `golden_real_docs` / CodeQL failing due to missing infrastructure |

### 6.6 Remediation cycle

| Item | Condition |
|---|---|
| Right to fix | The delivering party may fix any valid defect reported within the review window |
| Re-test rounds | **One round** for the original rejection list (unless the parties agree in writing to more) |
| Re-test scope | Limited to the issues in the original rejection notice — no new issues are opened in that round |
| Once fixed | Once the listed defect is fixed and the relevant AT passes, that part is immediately treated as accepted |
| Timing | Set jointly based on severity; delay caused by the accepting party (e.g. withholding environment access or not responding) does not count against the delivering party |

### 6.7 Outcomes

**On pass:** the system is accepted within the §4.1 scope and the §4.3 conditions that were met; warranty
and support per §7 begin (subject to §8); carve-outs from §9/§4.4 remain outside liability/warranty as
disclosed; further work is a change request.

**On a valid conditional rejection:** the delivering party remediates per §6.6; parts that already passed
may still be accepted separately; a rejection never converts an out-of-scope item into something that
must be delivered.

---

## 7. Warranty and support

### 7.1 Definitions

| Term | Meaning |
|---|---|
| Warranty start date | The date acceptance becomes effective under §6 (including deemed acceptance/use, or a §11 signature) |
| Warranty period | The window in which the accepting party may report a covered defect |
| Covered defect | A §6.1 defect within the §4.1 scope (or a fully-conditioned §4.3 item), reproducible on the delivered environment/configuration |
| Sole remedy | The only remedy under this warranty: a fix or patch restoring delivered behavior |
| Support | Practical, operational help within the scope below — separate from defect warranty and from new feature work |
| Change request | Work outside this warranty/support scope, requiring separately agreed scope, timeline, and terms |

### 7.2 Warranty scope

| Item | Detail |
|---|---|
| Covered | Valid defects in the delivered software/config at `v1.0.0` @ `b9c9436`, within §4.1 scope and any fully-conditioned §4.3 item |
| Behavior reference | Behavior demonstrable from the real system and/or the §5 acceptance tests at delivery time — not marketing copy or a stale `.md` file |
| Duration | **7 days** from the warranty start date |
| Claim notice | Written, within the warranty period, with a reproducible procedure, environment, and supporting evidence |
| Remedy (sole remedy) | Limited to a code/config fix, a patch, or remediation guidance restoring delivered behavior |
| Not included in remedy | Refunds, damages, long-term replacement service, or any guarantee of business outcomes — see §8 |

**Claim conditions:** reported within the warranty period; shown to be a defect within scope (not a §9/
§4.4 carve-out); reproducible on a reasonable environment per this document; the accepting party
cooperates reasonably (logs, test environment, reproduction steps); and the system is still on the
delivered baseline, or only carries changes the delivering party approved or that clearly caused the
issue.

### 7.3 Warranty exclusions

The warranty does **not** cover: modification by anyone other than the delivering party without written
consent; a changed environment (OS, package versions, network, infrastructure) diverging from what was
delivered/recommended; external services (LLM gateway, token quota, network, DNS, TLS, domain, the
accepting party's GPU host); the quality, accuracy, or usage rights of the accepting party's own data;
misuse or running demo mode (`AUTH_REQUIRED=false`) in a real/open-network environment; out-of-scope
items and dead code per §4.4/§9; supplementary-suite failures caused by missing infrastructure; new
requirements; or business-level expectations about AI answer correctness. Force majeure is excluded per
§8.6.

### 7.4 Post-delivery support

| Item | Detail |
|---|---|
| Nature | Best-effort, during normal working hours — not 24/7, no on-call |
| Duration | From the warranty start date until **31 July 2026**, or the end of the warranty period, whichever comes first — unless the parties agree in writing to extend |
| Channel | tedd0781@gmail.com, or a channel the accepting party specifies |
| Included | Operational questions about using the delivered system, pointers within this document set, and reasonable help distinguishing a defect from an environment issue |
| Not included | SLA/uptime, long-term monitoring, managing the gateway/infrastructure on the client's behalf, new feature development, large data migration, or full training programs beyond what's agreed |

**No implied SLA.** This document set creates no uptime, response-time, or service-level obligation
unless a separate service agreement exists. Latency/throughput numbers observed in one demo or
environment are not a performance guarantee for every environment. LLM gateway availability is the
accepting party's responsibility per §4.3 and §9.

### 7.5 Work that is a change request, not warranty/support

New features or scope expansion beyond `v1.0.0` @ `b9c9436`; making an out-of-scope item (§4.4) or dead
code (§9) fully functional; new external integrations; organization-specific UI/report/workflow
customization; ongoing operations, on-call, or SLA service; and migrating/repairing/cleaning the
accepting party's own business data — all require a separately agreed scope, timeline, and terms before
work starts.

---

## 8. Exclusions and limitation of liability

### 8.1 Interpretation

This section governs liability. Where it conflicts with §7 on the subject of liability, this section
controls for exclusions/caps; §7's sole-remedy warranty mechanic still applies to covered defects. Nothing
here is intended to exclude any liability that applicable law does not permit the parties to exclude by
agreement — but it does limit whatever liability the parties *can* agree to limit.

### 8.2 General exclusions (not the delivering party's liability on their own)

**External resources and services:** LLM gateway/token quota availability, speed, cost, and provider
errors; network/domain/TLS, internal connectivity, tunnels, and certificates; host/GPU hardware, power,
and cooling; and backup infrastructure beyond what ships in the software.

**The accepting party's data and use:** quality of ingested documents (poor OCR input, incomplete
documents, missing usage rights, or inaccurate content); results that depend on that data; production
configuration choices, including security toggles and credential rotation; running demo mode or exposing
the system to an open network without proper hardening; and unauthorized modification of code,
configuration, or dependencies.

**Out of scope and disclosed limitations:** everything in §4.4, all of §9, any §4.3 item whose conditions
aren't met, and any continuous service/SLA work per §4.4/§7.

**Non-binding documents:** `README.md`, `CHANGELOG.md`, other `docs/*.md` files, landing-page marketing
copy, and any promotional material with no working service behind it are **not representations or
commitments**. Where they conflict with the real system, the real system plus §4/§9/this section control.

### 8.3 AI answers are decision support

1. System answers are a **decision-support tool** — not a final determination and not an automatic
   operational instruction.
2. Users must verify answers against citations and source documents before acting on them, particularly
   for safety, machinery, lockout/tagout, and maintenance work.
3. The delivering party is **not liable** for decisions, actions, or business outcomes that rely on
   system answers.
4. An answer that doesn't match business expectations, while the system behaved as delivered, is not
   automatically a liability-triggering defect.

### 8.4 Security and use

The software ships with authentication, RBAC, rate limiting, encryption, and related security mechanisms
within the §4.1 scope. Configuring a secure production deployment, rotating secrets, managing user
permissions, and controlling network access are the accepting party's responsibility. No liability
attaches when the accepting party runs demo mode in a real environment, exposes the system to the
internet without hardening, or neglects credential rotation after hand-off (§10).

### 8.5 Exclusion of consequential damages

To the extent permitted by law, the delivering party is **not liable** for indirect, consequential, or
special damages, lost profits or revenue, business or production interruption, loss or corruption of
data (beyond the software delivery duty itself), cost of substitute goods or services, or loss of
reputation or business opportunity — arising from or related to use, inability to use, or the output of
the system, even if advised of the possibility of such damages.

### 8.6 Scope and limitation of liability (employment context)

**Underlying fact:** Neo Chat v1.0.0 is a work product the delivering party created **while performing
duties as an employee** (Backend / AI Developer) of the Center. **Compensation for this work is already
included in the delivering party's salary.** This delivery carries no separate fee or service charge.

| Item | Detail |
|---|---|
| Scope of liability | The delivering party's total liability under this delivery, whether in contract, tort, or otherwise |
| Limitation | Because this work was performed as an employee and **carries no separate fee**, the parties agree the delivering party's liability is **limited to what the employer–employee relationship and applicable law provide** — no numeric liability cap is set, because there is no fee amount to peg one to |
| Consequential damages excluded regardless | Liability never extends to indirect/special/consequential damages or loss of profit/data/opportunity as listed in §8.5 |
| Intellectual property | Work created during employment vests in the employing organization under applicable law and policy; the delivering party asserts no separate commercial ownership claim over the delivered system |
| Relationship to other sections | This limitation does not reduce the exclusions/consequential-damages cut in this section, and does not turn the §7.2 sole remedy into an automatic monetary payment |

Because there is no separate fee for this work, **no numeric liability cap applies**. The §7.2 sole
remedy (fix within the warranty period) is the primary remedy; the exclusions and consequential-damages
cut in this section remain in force alongside it.

### 8.7 Force majeure

The delivering party is not liable for delay, failure, or inability to perform caused by force majeure or
events reasonably outside its control — natural disaster, war, terrorism, government action, pandemic,
large-scale power/network outage, or failure of an external service the system depends on.

### 8.8 Who is responsible for what

| Topic | Delivering party | Accepting party |
|---|---|---|
| In-scope defect (§6/§7) | Fix under sole remedy, within the warranty period | Report it; cooperate with reproduction |
| LLM gateway / quota | Not liable for availability | Procure and maintain |
| Infrastructure / network / TLS | Deliver software and guidance within scope | Procure, configure, maintain |
| Real factory documents | Not liable for data quality | Owns the data and usage rights |
| AI answers / decisions | Not liable for decisions made from them | Verify against citations before acting |
| Out-of-scope items / dead code | No obligation to bring these to life by default | Change request if wanted |
| Credentials after hand-off | Transferred per §10 | Rotate and safeguard |

---

## 9. Known limitations and disclosed carve-outs

**Purpose of this section:** disclose, before acceptance, everything that's a known limitation of the
product or a piece of dead/orphaned code found in the repository at delivery time — so both parties
acknowledge it together. **Items in this section are carve-outs, not defects** of the §4.1 scope, and are
not grounds to refuse acceptance once §5's criteria pass on a suitable environment.

| Term | Meaning here | Effect on acceptance |
|---|---|---|
| Limitation | Real, existing behavior whose complete result depends on an external factor, or that is deliberately bounded | Not a defect if consistent with §4.3 / this section |
| Dead / orphaned code | UI, config, DB model, or compiled (`.pyc`) traces with no source/endpoint sufficient to call them delivered | Out of scope (§4.4) — does not need to be "brought to life" before acceptance |
| Legacy / deprecated config | An old variable or backend the system still detects/warns about but does not support as a production path | A misconfiguration on the accepting party's side is not a software defect |

### 9.1 Product-behavior limitations (L-series)

| Code | Limitation | Not a defect when… |
|---|---|---|
| L-01 | Depends on an external LLM gateway — quality, availability, speed, and cost depend on the gateway/quota the accepting party supplies | The gateway is down, quota is exhausted, or the accepting party's network can't reach it |
| L-02 | AI answers are decision support, not an absolute verdict — must be checked against citations, especially for safety work | A user misreads an answer without checking source documents, or asks about content outside the ingested library |
| L-03 | Vision extraction for drawings depends on the model/gateway; long jobs may hit edge/proxy timeouts | Quality/success varies with the vision profile/quota in use |
| L-04 | GPU sidecar is an optional accelerator, not mandatory at every site | No GPU is present and the system falls back as configured |
| L-05 | Voice is browser Web Speech only — there is no server-side Whisper transcription endpoint | Voice needs server-side transcription that was never delivered |
| L-06 | Text-to-SQL requires an external database the accepting party configures with read access | No external data source is registered |
| L-07 | Partial i18n — the main app is Thai-first | The system is expected to be fully translated app-wide |
| L-08 | `AUTH_REQUIRED=false` demo mode is not production-appropriate | The accepting party enables demo mode itself in an unsuitable environment |
| L-09 | Observability overlay (Prometheus/Grafana) is optional | It isn't enabled at every site by default |
| L-10 | Answer/retrieval quality depends on the ingested source documents | The accepting party's own source documents are unclear, low-quality, or out of profile |
| L-11 | Changing the embedding model/dimension forces a full re-ingest | This is an operational constraint, not a bug in the existing Q&A path |
| L-12 | Concurrent load on a shared gateway can hit budget/timeout limits; a global in-flight cap exists in config (may default off) | A high-load SLA was never agreed as an AT-* criterion |
| L-13 | Some dev profiles point at a local Ollama instance that may not exist on the real host | The correct profile/gateway per the deployment docs is not selected |
| L-14 | Advanced agentic/routing modes may sit behind a flag/canary; the product default favors the document-grounded RAG path | Not every agentic mode is proven as an AT-* condition unless separately agreed |

### 9.2 Dead code / orphaned surface (D-series) — consistent with §4.4

Roughly **50+ unique `.pyc` modules** exist under `src/` with no corresponding `.py` source at this
reference point. None of this is delivered source.

| Code | Item | Evidence |
|---|---|---|
| D-01 | Insights/Analytics UI with no backend | `web/lib/api/insights.ts`, `web/components/insights/` (~10 files); no `insights` router in `src/spark/api/v1/router.py` |
| D-02 | Predictive / DeepAnalyze — `.pyc` only, no source | `src/spark/integrations/predictive/`, `deepanalyze/` — mostly `__pycache__`; env keys like `MCP_PREDICTIVE_URL`, `PREDICTIVE_BACKEND`, `DEEPANALYZE_*` create no feature commitment |
| D-03 | Whisper / transcribe API — no endpoint | Client/env traces and a `whisper_service` `.pyc` exist; no transcription API ships |
| D-04 | A larger group of endpoints/services surviving only as `.pyc` | Representative names: `insights`, `predictive`, `inventory`, `analytics`, `alerts`, `rca`, `handover`, `work_orders`, `components`, `observability`, `specialized`, and matching service/model modules |
| D-05 | Legacy product dashboard page | Current `web/app/` has no dashboard as the primary surface; `/system-admin` is separate and in scope |
| D-06 | `Component` / `ComponentAlias` entities | Model exists in `src/spark/db/models/org.py`; no full product surface/API |
| D-07 | RAGFlow and other legacy config | Production path is native ingest only; `src/spark/core/deprecated_config.py` warns on legacy `RAGFLOW_*` keys; `scripts/audit_dead_code.sh` forbids `ragflow` references in `src/` |

**Interpretation:** the presence of `.pyc` remnants from earlier development is not a delivery of that
feature, and does not obligate the delivering party to restore that source as part of this acceptance
round.

### 9.3 Dead-code / legacy audit process delivered

| Item | Detail |
|---|---|
| Script | `scripts/audit_dead_code.sh` (invoked by the `python` job in `.github/workflows/ci.yml`) |
| What it checks | Validates config docs; runs `vulture` at a non-strict confidence threshold (≥ 80); forbids `ragflow` references in `src/` |
| Startup audit | `audit_deprecated_config()` logs metrics/warnings when a legacy key is present |
| Delivery meaning | The delivering party ships an anti-regression mechanism for legacy config — this is not a guarantee that every `.pyc` on disk is gone |

### 9.4 Operational limitations — accepting party's responsibility

| Code | Item | Note |
|---|---|---|
| O-01 | Infrastructure | Host, GPU (if used), network, domain, TLS, firewall |
| O-02 | LLM gateway / quota | Keys, budget, token quota |
| O-03 | Real documents and rights | Preparing/authorizing factory documents for ingestion |
| O-04 | Post-hand-off secrets | Rotating JWT/DB/API keys/OAuth |
| O-05 | Test/production DB separation | Do not run the test suite directly against production — it can create artifacts/false alerts |
| O-06 | Backups | Postgres + Qdrant + MinIO must be in the accepting party's backup plan |
| O-07 | 24/7 SLA / on-call | Not included in this delivery round |
| O-08 | CI/CD account/runner | Configuring CI on the accepting party's own account is operational work, not an AT-* criterion by itself |

### 9.5 What must never be interpreted as a defect

1. Insights/Predictive/Whisper/legacy dashboard being non-functional, per §9.2 and §4.4.
2. Effects of a gateway outage, exhausted quota, or slow network.
3. Answer quality against low-quality documents the accepting party ingested itself.
4. Performance differences when no GPU sidecar is present.
5. Absence of app-wide i18n or of a Whisper server.
6. The accepting party setting `AUTH_REQUIRED=false` in an open environment.
7. chaos/nightly/`golden_real_docs` suite failures when supporting infrastructure is incomplete.
8. Landing-page marketing copy describing a capability with no backend.
9. An `.env.example` variable with no real consumer.
10. `.pyc` remnants with no `.py` source.

### 9.6 Carve-out summary for acceptance day

| Topic | Classification | Must be fixed before acceptance? |
|---|---|---|
| AT-01…AT-05 failing on a correct environment | Possible defect under §6 | Yes (within §4.1 scope) |
| Gateway not available | Limitation L-01 / §4.3 | No — defer proof of that gateway-dependent part |
| Insights UI non-functional | Dead code D-01 / §4.4 | No |
| Predictive/DeepAnalyze has no source | D-02 / §4.4 | No |
| No Whisper server | D-03 / L-05 | No |
| `Component` entity surface incomplete | D-06 / §4.4 | No |
| A new feature requested after v1.0.0 | Change request | No — does not block on §9/§4.4 |

---

## 10. Confidential credential hand-off

This section covers **DEL-10** from §4.2. **No secret value appears anywhere in this document set or in
any file under `temp/tabs/` or similar working folders.** Only key/group names and process steps are
shown here; actual values move through a separate secure channel only.

### 10.1 Principles

1. **Never embed secret values** in delivery documents, public tickets, or commits.
2. **Transfer through a channel separate from this document** — in person is preferred, or an encrypted
   channel both parties agree on.
3. **The accepting party must rotate** important secrets after hand-off, especially anything used during
   development/testing.
4. **`JWT_SECRET` must match** between the API (`.env`) and the web app (`web/.env.local`) — rotate them
   together.
5. Once transfer/rotation is complete, **the delivering party is not liable** for leakage or misuse
   arising from how the accepting party stores the secret afterward (consistent with §8).
6. Any leftover key for an out-of-scope service (e.g. DeepAnalyze) is optional/out of scope per §9 and
   creates no feature commitment.

### 10.2 Key groups that may need transfer (names only — no values)

The full, current inventory — including exactly which secrets exist on the delivery machine today, where
they live, and the recommended rotation order — is maintained in
[`docs/HANDOVER.md` §15, "Credentials & secrets inventory"](./HANDOVER.md#15-credentials--secrets-inventory).
This section restates the groups for the acceptance record; **treat `docs/HANDOVER.md` §15 as the
authoritative, current list** since it is verified against the actual `.env`/deployment state.

| Group | Representative keys | Note |
|---|---|---|
| A. App & auth | `JWT_SECRET`, `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, `AUTH_REQUIRED` | `JWT_SECRET` must be rotated on both API and web together |
| B. Database & data-source encryption | `POSTGRES_PASSWORD`, `POSTGRES_SQL_READONLY_PASSWORD`, `DATA_SOURCE_ENCRYPTION_KEY` | Rotate the encryption key carefully — it re-encrypts stored external data-source credentials |
| C. LLM / embedding / rerank gateway | `KKU_API_KEY`, `OLLAMA_API_KEY` / `OLLAMA_EMBED_API_KEY`, `FORGE_API_KEY` / `FORGE_EMBED_API_KEY` / `FORGE_RERANK_API_KEY` | Gateway availability after rotation is the accepting party's responsibility per §4.3/§9 |
| D. Object storage / audit | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` or `S3_SECRET_KEY`, `AUDIT_EXPORT_HMAC_SECRET` | Rotate and update dependent config |
| E. Optional / legacy environment | `LANGCHAIN_API_KEY`, `DEEPANALYZE_API_KEY`, any GitHub PAT that was ever on the dev machine | DeepAnalyze key is out of scope per §9; revoke any exposed GitHub PAT on GitHub itself |

### 10.3 Access that isn't an env value but still needs transfer/confirmation

Git repository access at the delivered tag; any host/SSH access if a physical/cloud machine is handed
over; the initial seeded admin account (change its password immediately); Grafana/observability default
credentials if enabled; and ownership of gateway/OAuth provider consoles.

### 10.4 Transfer process

| Step | Activity |
|---|---|
| 1 | Prepare the checklist — use §10.5 below, checking only the keys that actually exist in the delivered environment |
| 2 | Transfer in person, or via an encrypted channel both parties agree on — never paste values into this document |
| 3 | The accepting party signs §10.5 confirming receipt of the checked items (no values attached) |
| 4 | The accepting party rotates important secrets within the agreed time (recommended: immediately after hand-off) |
| 5 | Verify after rotation — login, `/readyz`, and a basic chat path once the gateway is ready |
| 6 | Once steps 3–5 are done, responsibility for that secret moves to the accepting party |

**Recommended rotation order:** (1) revoke any old GitHub PAT and confirm the remote uses a token-less
URL; (2) rotate gateway keys with each gateway owner and confirm the new team's quota; (3) generate a
fresh `JWT_SECRET` on both API and web at the same time; (4) rotate DB/MinIO/OAuth secrets;
(5) carefully rotate `DATA_SOURCE_ENCRYPTION_KEY` if external data sources are in use; (6) verify
`/readyz` and core paths after rotation.

### 10.5 Credential hand-off confirmation (no values recorded)

| Group / item | Received (yes/no/n·a) | Rotated (yes/no/scheduled) | Date |
|---|---|---|---|
| `JWT_SECRET` (API + web) | .............. | .............. | .............. |
| `POSTGRES_*` passwords | .............. | .............. | .............. |
| `DATA_SOURCE_ENCRYPTION_KEY` | .............. | .............. | .............. |
| Gateway keys (KKU/Ollama/Forge as used) | .............. | .............. | .............. |
| Google OAuth secrets | .............. | .............. | .............. |
| MinIO / S3 secrets | .............. | .............. | .............. |
| `AUDIT_EXPORT_HMAC_SECRET` | .............. | .............. | .............. |
| Git / host / initial admin access | .............. | .............. | .............. |
| Other (specify) | .............. | .............. | .............. |

**Channel used:** ☐ In person ☐ Agreed encrypted channel ☐ Other: ______________________

**Responsibility status:** ☐ Moved to the accepting party after transfer/rotation ☐ Rotation still pending

### 10.6 Never do this

1. Copy values from `.env`, key files, or `web/.env.local` into a delivery document or a public ticket.
2. Send secrets over unencrypted email/chat without an agreed channel.
3. Treat a key's presence in `.env.example` as a guarantee that it has a real, working value at the
   accepting party's site.
4. Use an out-of-scope service key (e.g. DeepAnalyze) as an acceptance condition for a feature that was
   never delivered.

---

## 11. Acceptance certificate

Reference document ID: **NEOCHAT-DELIVERY-2026-001**

### 11.1 Delivery information

| Item | Value |
|---|---|
| Product / version | Neo Chat 1.0.0 |
| Git tag / commit | v1.0.0 / `b9c9436` |
| Ready-for-review date | ....../....../.......... |
| Review window ends | ....../....../.......... (per §6.4: +3 business days) |
| Acceptance sign-off date | ....../....../.......... |
| Signing location | .............................................. |

### 11.2 Acceptance outcome (choose one)

| ☐ | Outcome | Meaning |
|---|---|---|
| ☐ | Full acceptance | Passes §6 and AT-01–AT-05 per §5; no open blocking defect |
| ☐ | Conditional acceptance | Accepted, with the punch list below, which does not void acceptance of what already passed |
| ☐ | Deemed acceptance | Review window elapsed with no valid written rejection, per §6.4 |
| ☐ | Deemed use | The accepting party has put the system into real/production use, per §6.4 |
| ☐ | Rejected | A valid written rejection exists — detail the reproducible AT/procedure below |

### 11.3 Mandatory criteria summary (per §5)

| Code | Item | Result | Date |
|---|---|---|---|
| AT-01 | `scripts/test.sh` | ☐ Pass ☐ Fail ☐ Not run* | .............. |
| AT-02 | contracts pytest | ☐ Pass ☐ Fail ☐ Not run* | .............. |
| AT-03 | Playwright e2e | ☐ Pass ☐ Fail ☐ Not run* | .............. |
| AT-04 | web `npm test` | ☐ Pass ☐ Fail ☐ Not run* | .............. |
| AT-05 | CI parity (a/b/c) | ☐ Pass ☐ Fail ☐ Not run* | .............. |

\* "Not run" requires a reason consistent with §6.2 (e.g. the accepting party's environment wasn't
ready) and is not, by itself, grounds to reject the software.

### 11.4 Deliverables summary (per §4.2)

| Code | Item | Received |
|---|---|---|
| DEL-01 | Source at tag v1.0.0 | ☐ Yes ☐ No ☐ Partial |
| DEL-02…DEL-08 | Compose/Docker, configs, migrations, scripts/ops, tests, this delivery package | ☐ Yes ☐ No ☐ Partial |
| DEL-05 / DEL-09 | GPU sidecar / sample documents (as agreed) | ☐ Yes ☐ Not requested ☐ Partial |
| DEL-10 | Credentials (transferred per §10) | ☐ Yes ☐ Scheduled ☐ Not used this round |

### 11.5 Acknowledgment of key terms

By signing, the accepting party confirms it has read and accepts, at minimum:

1. The delivered / partial / out-of-scope split in §4.
2. The mandatory acceptance criteria in §5 and the conditions in §6, including deemed acceptance / deemed
   use.
3. The limitations and dead code in §9 are not defects by default.
4. The sole-remedy warranty and no-SLA terms in §7.
5. The exclusions and consequential-damages cut in §8 — this work was performed as an employee, its
   compensation is already in salary, there is no separate fee, and liability is therefore limited per
   the employment relationship with no numeric cap.
6. Credentials transfer through a separate channel, and responsibility moves per §10.
7. AI answers are decision support; users must check citations/source documents.

| ☐ | Item acknowledged |
|---|---|
| ☐ | §4 (scope) |
| ☐ | §5 and §6 (criteria / acceptance conditions) |
| ☐ | §9 (limitations and dead code) |
| ☐ | §7 and §8 (warranty / liability) |
| ☐ | §10 (credentials) |

### 11.6 Punch list

Use this when "conditional acceptance" is selected, or for follow-up items that don't reject the whole
delivery. *As of the date this document was written, there is no open punch-list item — the table below
is left blank for acceptance day, if needed.*

| # | Item | Category* | Owner | Due |
|---|---|---|---|---|
| 1 | .............................................. | .............. | .............. | .............. |
| 2 | .............................................. | .............. | .............. | .............. |
| 3 | .............................................. | .............. | .............. | .............. |

\* Category: defect (in scope) / §4.3 condition unmet / carve-out / change request / other

### 11.7 If rejected

| Item | Detail |
|---|---|
| Rejection notice date | ....../....../.......... |
| AT / reproducible procedure | .............................................. |
| Environment used | .............................................. |
| Actual result | .............................................. |
| Why it falls within §4.1 scope | .............................................. |

A rejection with no reproducible procedure, or that cites only §4.4/§9 items or gateway unavailability,
is not a valid rejection under §6.4.

### 11.8 Warranty start

| Item | Value |
|---|---|
| Warranty start date (§7) | ....../....../.......... |
| Warranty end date (+7 days) | ....../....../.......... |
| Support ends (§7.4) | No later than 31 July 2026, or the end of the warranty period, whichever comes first, unless extended in writing |

### 11.9 Deemed-acceptance reminder

Per §6.4: if no valid written rejection is received within the **3-business-day** review window from the
ready-for-review date, the accepting party is treated as having fully accepted the system — even without
a signature on this page.

### 11.10 Signatures

| Delivering party | Accepting party's authorized signatory |
|---|---|
| Signature: .............................................. <br> Printed name: Narinthon Yangngam <br> Title: Backend / AI Developer <br> Organization: CPF Center of Engineering Excellence — Repair and Development Center for Prepared Food Machinery Engineering <br> Date: ....../....../.......... | Signature: .............................................. <br> Printed name: ........................................ <br> Title: .............................................. <br> Organization: .............................................. <br> Date: ....../....../.......... |

#### Witness (if applicable)

| Witness — delivering party | Witness — accepting party |
|---|---|
| Signature: .............................................. <br> Name: .............................................. <br> Date: ....../....../.......... | Signature: .............................................. <br> Name: .............................................. <br> Date: ....../....../.......... |

---

## 12. Definitions

| Term | Meaning in this document |
|---|---|
| RAG | Retrieval-Augmented Generation — retrieve documents, then generate a grounded answer from them |
| Grounded answer | An answer tied to retrieved evidence, with citations back to source documents |
| Fail-closed | When evidence is insufficient, the system declines (`NO_DATA`) rather than guessing |
| Defect | See §6.1 |
| Carve-out | See §9 header — a disclosed limitation or out-of-scope item, not a defect |
| Deemed acceptance / deemed use | See §6.4 |
| Sole remedy | See §7.1 — the only remedy under the warranty is a fix/patch |
| Change request | Work outside the delivered scope and warranty/support, requiring separate agreement |
| AT-01…AT-05 | The five mandatory acceptance tests defined in §5 |
| L-series / D-series / P-series / X-series | Codes used across this document for limitations (L), dead code (D), partially-delivered items (P), and out-of-scope items (X) |

---

## 13. Document history

| Date | Change |
|---|---|
| 2026-07-20 | Internal Thai-language working reference drafted (document control ID NEOCHAT-DELIVERY-2026-001) |
| 2026-07-21 | This English delivery-and-acceptance edition adapted for the repository, verified against `main` @ `721cae7` (which sits at/after the `v1.0.0`/`b9c9436` reference point), and cross-linked with `docs/HANDOVER.md` |

*This document and [`docs/HANDOVER.md`](./HANDOVER.md) together form the Neo Chat v1.0.0 delivery record.
Keep both current; if either diverges from the delivered code, fix the document — the code is the source
of truth per [§0.2](#02-relationship-to-other-documents--order-of-precedence).*
