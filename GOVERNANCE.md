# Governance

How Neo Chat is developed, reviewed, and released on GitHub.

## Branches

| Branch | Role | Who merges |
|--------|------|------------|
| `develop` | Daily integration; all feature PRs target here | Maintainers after green CI + review |
| `main` | Production-ready; release PRs only | Maintainers after release checklist |
| `feat/*`, `fix/*`, `chore/*`, … | Short-lived work | Author opens PR → delete after merge |

**Flow:** feature PR → `develop` → release PR `develop` → `main` → semver tag.

Hotfixes branch from `main`, merge to `main`, then backport to `develop`.

## Pull requests

- **One branch = one PR** — keep scope focused.
- **Merge commit only** — no squash merges (preserves audit trail).
- **CI must be green** before merge — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
- **CODEOWNERS** auto-request review on sensitive paths — see [`.github/CODEOWNERS`](.github/CODEOWNERS).
- Fill the [PR template](.github/pull_request_template.md); update [`CHANGELOG.md`](CHANGELOG.md) for user-visible changes.

## Quality gates

| Gate | When |
|------|------|
| Ruff + pytest | Every PR (Python) |
| tsc + ESLint + unit tests + build | Every PR (web) |
| Playwright E2E | Every PR (web) |
| Held-out leakage audit | Every PR to `develop` |
| RAG baseline eval | Path-filtered — RAG/ingestion changes |
| Adversarial eval subset | Path-filtered — RAG/safety/eval config changes |
| CodeQL | Every PR + weekly schedule |
| Dependabot | Weekly dependency PRs — review before merge |

## Releases

Production releases to `main` require a green [`scripts/release_gate.sh`](scripts/release_gate.sh) run (leakage audit, held-out, adversarial, contract tests, ingest validation, and Tier 2 baseline lock when `--profile production`).

- Version tags follow semver (`v0.x.y`) aligned with GitHub milestones.
- Release notes come from [`CHANGELOG.md`](CHANGELOG.md).
- Package version in `pyproject.toml` is metadata only — tags are the source of truth.

See [`configs/remediation/phase_gates_v3.yaml`](configs/remediation/phase_gates_v3.yaml) for maintainer release automation notes.

## Security

- Report vulnerabilities via [`SECURITY.md`](SECURITY.md) — private advisories preferred.
- Dependabot and CodeQL run on `develop` and `main`.
- Production deploys must set `APP_ENV=production` and rotate `JWT_SECRET`.

## Community

- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) applies to all project spaces.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) is the onboarding guide for new contributors.

---

See also: [CONTRIBUTING.md](./CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) · [SECURITY.md](./SECURITY.md)
