# Neo Chat Demo Playbook

A script for giving a live demo of Neo Chat, from a clean environment
through the core document Q&A loop and into the optional admin/advanced
segments. Written from the actual product surface — see
[`docs/admin-guide.md`](./admin-guide.md) and
[`docs/architecture.md`](./architecture.md) for the full detail behind each
step.

## Contents

- [Before the demo](#before-the-demo)
- [Core loop (5–7 minutes)](#core-loop-57-minutes)
- [Optional: admin console tour (5 minutes)](#optional-admin-console-tour-5-minutes)
- [Optional: Text-to-SQL / analytics question](#optional-text-to-sql--analytics-question)
- [Optional: System Admin / Control Room](#optional-system-admin--control-room)
- [Optional: quarantine & release](#optional-quarantine--release)
- [Talking points / what to say](#talking-points--what-to-say)
- [If something breaks mid-demo](#if-something-breaks-mid-demo)

## Before the demo

**Environment**: run this against a real deployment
([`deploy/README-ONPREM.md`](../deploy/README-ONPREM.md)) or a local dev
stack (`./scripts/dev.sh`, or see
[`CONTRIBUTING.md` § Quick bootstrap](../CONTRIBUTING.md#quick-bootstrap)).
Confirm health first:

```bash
curl http://localhost:8000/readyz
```

**Get an admin account.** There is currently no working one-shot demo-seed
script (`scripts/seed_demo.py` is referenced in a couple of places —
`CONTRIBUTING.md`'s older instructions, `deploy/setup_onprem.sh --seed` —
but doesn't exist in this branch; don't rely on it). If you don't already
have an admin login, create the first one directly:

```bash
uv run python - <<'PY'
import asyncio, uuid
from spark.core.auth import hash_password
from spark.core.database import AsyncSessionLocal
from spark.db.models.org import Role, User, UserRole

async def main():
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        # Run scripts/init_db.py first if this raises "no row found" — it seeds the roles table.
        role = (await session.execute(select(Role).where(Role.role_code == "admin"))).scalar_one()

        user = User(
            username="demo_admin",
            full_name="Demo Admin",
            email="demo_admin@example.com",
            password_hash=hash_password("ChangeMe123!"),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        await session.commit()
        print(f"created admin: {user.username} / ChangeMe123!")

asyncio.run(main())
PY
```

Once you have one admin, every subsequent user should be created normally
from the Users tab (see
[Admin Guide § Users tab](./admin-guide.md#users-tab)) — this bootstrap
step is only for a genuinely empty database.

**Have a factory to demo into.** If none exists yet, create one from
`/admin/factories` first — see
[Admin Guide § Factory management](./admin-guide.md#factory-management-adminfactories).

**Pick a document.** Anything readable works, but a short manual, SOP, or
spec sheet with a few concrete facts (part numbers, thresholds, steps) makes
for the most convincing citation demo. Avoid anything with sensitive real
data if the audience isn't cleared for it.

## Core loop (5–7 minutes)

1. **Log in** as the admin (or a demo operator account) at `/login`.
2. **Upload**: go to `/upload`, choose the document, pick the closest
   document type (e.g. `machine_manual`, `sop`). Submit.
3. **Watch it ingest**: the job list streams live progress
   (parse → trust scan → chunk → index). Point out that this is a real
   pipeline, not a canned demo state — narrate the stages as they tick by.
4. **Confirm it landed**: open `/documents`, find the new document, open
   it to show the original file rendered in the viewer.
5. **Ask a question** in `/chat` that the document can actually answer —
   ideally something specific (a number, a step, a part name), not just
   "what is this document about."
6. **Open a citation** on the answer — click through to the exact page/
   passage the answer was grounded in. This is the single most important
   moment of the demo: **the answer is traceable to source**, not a
   plausible-sounding guess.
7. **Ask something the document can't answer** (a fact from a different
   domain entirely). The system should say it doesn't have enough
   information rather than inventing an answer — this fail-closed behavior
   is worth calling out explicitly (see
   [Talking points](#talking-points--what-to-say)).
8. **Submit feedback** on one answer (thumbs-down / report flow) to show
   the loop closes — someone downstream will see this in
   [`/feedback`](./admin-guide.md#feedback-triage-feedback).

## Optional: admin console tour (5 minutes)

From `/admin`:
- **Users** — create a user live, show the one-time temporary-password
  reveal, mention factory-scoped and job-position-scoped access.
- **Job Positions** — show how a document can be restricted to a role
  (e.g. only "QC" sees a QC-only SOP).
- **API keys** — mention this is how a partner system integrates
  server-to-server (see
  [`docs/public-api-integration.md`](./public-api-integration.md)) without
  going through the web login at all.

From `/admin/factories` — show per-factory settings (retrieval `top_k`,
chunking strategy) if the audience is technical.

## Optional: Text-to-SQL / analytics question

If a demo external database is registered
([Admin Guide § External Postgres](./admin-guide.md#external-postgres-tab-text-to-sql)),
ask an analytic question in chat (e.g. "how many machines are due for
maintenance this month") and show that the answer comes from a **live,
read-only SQL query** against real data, not the document index — and can
even **combine** a SQL result with document context in one answer
(a "compound" question). This directly demonstrates that Neo Chat is not
limited to document retrieval, which is worth stating explicitly since
older internal docs incorrectly claimed otherwise.

Skip this segment entirely if no data source is configured — don't try to
register one live during a demo.

## Optional: System Admin / Control Room

Open `/system-admin` and let it sit on screen for a moment — the "NOC"
dashboard (traffic, latency, ingest status, dependency health) reads well
even without explaining every panel. If you want to demonstrate an
operational action, **"Sync Qdrant"** or toggling **maintenance mode**
(with a custom message) are the safest, most visibly-reversible choices.
Avoid "Clear cache" mid-demo unless you want the next few responses to be
visibly slower while caches rebuild. See
[Admin Guide § System Admin / Control Room](./admin-guide.md#system-admin--control-room-system-admin)
for what each panel and action actually does.

## Optional: quarantine & release

Upload a document containing something the content-safety scanner is
likely to flag (a fake PII string, or a document type with a strict trust
policy) to show the quarantine pill on `/documents`. Open it, show the
policy findings, and release it **as a different admin account than the
uploader** — the system enforces separation of duties here (the uploader
cannot release their own document), which is worth calling out as a
deliberate control, not a bug — see
[Admin Guide § Document release](./admin-guide.md#document-release-quarantine-review).

## Talking points / what to say

- **Grounded, not generative-only**: every answer is retrieved from
  actual ingested documents (or a live SQL query) before the model writes
  anything — the model is not answering from general knowledge.
- **Fail-closed**: when there isn't enough evidence, the system says so
  instead of guessing. This is a deliberate design choice, demonstrated in
  step 7 of the [core loop](#core-loop-57-minutes) — call it out by name.
- **Citations are real page/passage references**, not decoration — click
  through one live.
- **Multi-tenant by factory**: access is scoped per factory and per job
  position, so this isn't "one shared knowledge base with no boundaries."
- **Not just documents**: the Text-to-SQL path (if demoed) shows the
  system can also answer from live operational data, not only static
  documents.

## If something breaks mid-demo

| Symptom | What to do live |
| --- | --- |
| Chat says the AI is temporarily unavailable | The LLM gateway is likely down/rate-limited — acknowledge it plainly ("that's our upstream model provider, not the retrieval system"), and pivot to showing the retrieval/citation side of a *previous* answer instead of forcing a new question |
| A question that should be answerable returns "no data" | Don't panic-retry the same phrasing — rephrase once. If it persists, this is actually a good moment to demonstrate the fail-closed principle rather than a failure, if you frame it that way |
| Ingest job seems stuck | Check `/system-admin` → Ingest Jobs / Connectivity panels while talking through what's happening, rather than going silent — see [Operations Guide § Troubleshooting](./operations-guide.md#troubleshooting) if it doesn't resolve in a minute or two |
| Reranking feels slow | The GPU sidecar or rerank gateway may be down; the system automatically falls back to fusion-only scoring, so answers still work, just with slightly different ranking — no action needed mid-demo |

For anything not covered here, see the full
[Operations Guide § Troubleshooting](./operations-guide.md#troubleshooting)
table.

## Related docs

- [docs/admin-guide.md](./admin-guide.md) — full admin console reference
- [docs/architecture.md](./architecture.md) — how a question actually gets answered
- [docs/operations-guide.md](./operations-guide.md) — health checks and troubleshooting
- [docs/user-guide.md](./user-guide.md) — the non-admin operator's view of the product
