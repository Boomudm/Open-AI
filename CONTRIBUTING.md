# Contributing to Neo Chat

Thank you for helping improve Neo Chat. This guide covers local setup, branch workflow, and what we expect in pull requests.

## Before you start

1. Read [`README.md`](./README.md) for product context and [`docs/architecture.md`](./docs/architecture.md) for system design.
2. Check [open issues](https://github.com/CPF-Chula-CEDT-2026/spark/issues) — avoid duplicate work.
3. For security vulnerabilities, follow [`SECURITY.md`](./SECURITY.md) — **do not** open public issues.

## Development environment

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11 – 3.13 |
| Node.js | 20 LTS (for `web/`) |
| Docker | Latest (Postgres, Redis, Qdrant) |
| uv or pip | For Python deps |
| Ollama | Local LLM + embeddings (optional for full RAG) |

### Quick bootstrap

```bash
git clone https://github.com/CPF-Chula-CEDT-2026/spark.git
cd spark
git switch develop
git pull origin develop

cp .env.example .env
docker compose up -d
uv sync --extra dev          # or: pip install -e ".[dev]"
uv run alembic upgrade head
uv run python scripts/init_db.py     # creates tables (idempotent) + seeds default roles

# Terminal 1 — API
export PYTHONPATH=src
uvicorn spark.main:app --reload --port 8000 --app-dir src

# Terminal 2 — Celery
celery -A spark.workers.celery_app worker --concurrency=1 --loglevel=info

# Terminal 3 — Web
cd web && npm ci && npm run dev
```

`scripts/init_db.py` seeds roles only, not a login-able user — create your
first admin from a Python shell (`hash_password` + insert a `User` +
`UserRole`) or via another already-provisioned admin's
`POST /api/v1/admin/users`. There is no working `scripts/seed_demo.py` /
`scripts/seed_demo_docs.py` in this branch despite older references to them
elsewhere in the repo (including `deploy/setup_onprem.sh --seed`) — those
scripts don't currently exist; see
[`docs/demo_playbook.md`](docs/demo_playbook.md) for a demo-data path that
works today.

One-command alternative: `./scripts/dev.sh` (starts the full local stack;
still assumes the database is already initialized and seeded as above).

### Verify your change

**Python** (when `src/` or `tests/` changed):

```bash
uv run ruff check src tests
uv run pytest tests/ -q --tb=short
```

**Web** (when `web/` changed):

```bash
cd web
npx tsc --noEmit
npm run lint
npm test
npm run build
npm run test:e2e    # requires API + web running
```

**RAG / ingestion** (when retrieval or ingest paths changed):

```bash
uv run python scripts/evaluate_baseline.py \
  --config configs/evaluation_baseline_ci.yaml \
  --mode rag --deterministic-rag
```

## Branch workflow

| Branch | Purpose |
|--------|---------|
| `develop` | Integration — **target all feature PRs here** |
| `main` | Production-ready releases |
| `feat/*`, `fix/*`, `chore/*`, … | Short-lived work branches |

```bash
git switch develop && git pull origin develop
git switch -c feat/my-feature
# … work …
git push -u origin HEAD
gh pr create --base develop
```

**Never** push directly to `main` or `develop`.

Branches prefixed `archive/` are frozen snapshots kept for reference — never
build on them.

## Versioning & releases

- [SemVer](https://semver.org/); current version is **1.0.0**.
- The single source of truth for the current version is `pyproject.toml`; keep
  `web/package.json` and the FastAPI `version=` in `src/spark/main.py` in sync.
- To cut a release: move `[unreleased]` CHANGELOG entries under a new
  `## [X.Y.Z] — date` heading, bump the three version strings above, merge
  `develop` → `main`, then create one annotated tag `vX.Y.Z` on `main`.
- Tag history before 2026-07-18 was removed as inconsistent; the mapping of old
  tags to commits lives in
  [`docs/archive/release-tags-2026-07-18.md`](docs/archive/release-tags-2026-07-18.md).
  `CHANGELOG.md` is the authoritative release history.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(rag): add cross-encoder relevance gate
fix(web): repair Thai sidebar toggle labels
chore(docs): update deployment guide
```

- Split unrelated changes into separate commits/PRs.
- Reference issues: `closes #123` when applicable.
- Do **not** add `Co-authored-by` or `Made-with` trailers.

## Pull requests

1. Fill out the [PR template](.github/pull_request_template.md).
2. Update [`CHANGELOG.md`](./CHANGELOG.md) under `[unreleased]` for user-visible changes.
3. Update `README.md` if setup commands or public behavior changed.
4. Ensure CI is green before requesting review.
5. We use **merge commits** (not squash) when landing to `develop`.

### Review ownership

Path-based reviewers are defined in [`.github/CODEOWNERS`](.github/CODEOWNERS). Update your GitHub handle there when you join the core team.

## Issue labels

| Label | Use |
|-------|-----|
| `bug` | Defect with reproduction steps |
| `enhancement` | New feature or improvement |
| `refactor` | Internal restructuring, no behavior change |
| `docs` | Documentation only |
| `ci` | CI/CD, GitHub Actions, Dependabot |

Use the [bug report](.github/ISSUE_TEMPLATE/bug_report.yml) or [feature request](.github/ISSUE_TEMPLATE/feature_request.yml) templates when opening issues.

## Code style

- **Python:** Ruff (configured in `pyproject.toml`); type hints on public APIs.
- **TypeScript:** ESLint + Next.js config; prefer existing patterns in `web/lib/` and `web/components/`.
- **Docs:** English for contributor docs; Thai operator guides live under `docs/`.

## Questions

- Operator / deployment: [`docs/operations-guide.md`](./docs/operations-guide.md)
- Architecture: [`docs/architecture.md`](./docs/architecture.md)
- Support expectations: [`.github/SUPPORT.md`](.github/SUPPORT.md)
