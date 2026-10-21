# Release-tag archive — 2026-07-18 versioning cleanup

On 2026-07-18 all git tags were removed from this repository. The early tags mixed
three incompatible schemes (`vX.Y.Z`, phase markers `-p0…-p3`, and a premature
`v1.0.0`) and no longer matched the version recorded in `pyproject.toml` /
`web/package.json`. `CHANGELOG.md` remains the authoritative release history;
the release originally tagged `v1.0.0` is recorded there as **0.9.0** — the
project stays in 0.x until the API is declared stable.

Versioning restarts at **0.9.0** (current version in project metadata). The next
release should be tagged `v0.10.0` (or `v0.9.1` for a patch) on `main` at release
time — one annotated tag per release, matching its `CHANGELOG.md` heading.

## Deleted tags → commits

Every commit below is still reachable on `main`/`develop` history; only the tag
refs were removed. To inspect one: `git show <sha>`.

| Deleted tag | Commit | Date | CHANGELOG entry |
|---|---|---|---|
| `v0.1.0-p0` | `2d48dc1` | 2026-05-24 | — (phase marker, no release) |
| `v0.2.0-p1` | `e221b69` | 2026-05-24 | — (phase marker, no release) |
| `v0.3.0` | `0919be3` | 2026-05-24 | [0.3.0] |
| `v0.3.0-p2` | `0fd6235` | 2026-05-24 | — (phase marker, no release) |
| `v0.4.0` | `4c07ea0` | 2026-05-24 | [0.4.0] |
| `v0.4.0-p3` | `d79fde6` | 2026-05-24 | — (phase marker, no release) |
| `v0.4.1` | `8991644` | 2026-05-24 | [0.4.1] |
| `v0.4.2` | `0924e71` | 2026-05-24 | [0.4.2] |
| `v0.4.3` | `883db0b` | 2026-05-29 | [0.4.3] |
| `v0.4.4` | `dd28402` | 2026-05-29 | [0.4.4] |
| `v0.5.0` | `00d6c00` | 2026-06-14 | [0.5.0] |
| `v0.6.0` | `aaf8919` | 2026-06-14 | [0.6.0] |
| `v0.7.0` | `3f6ff2d` | 2026-06-19 | [0.7.0] |
| `v0.8.0` | `f2e23a4` | 2026-06-19 | [0.8.0] |
| `v0.8.1` | `21ba6f0` | 2026-06-19 | [0.8.1] |
| `v1.0.0` | `a788a56` | 2026-06-20 | [0.9.0] (renumbered from 1.0.0) |

## Related cleanup (same day)

- `main` was reset to `develop` (the previous `main` tip `3eb5283` — a run of
  untested auto-merged Dependabot bumps, PRs #236–#248 — is preserved on branch
  `archive/main-pre-cleanup-2026-07-18`).
- The 10 open Dependabot PRs (#290–#299) were closed and their branches deleted;
  Dependabot itself was already disabled. Dependency upgrades are now deliberate,
  tested on the Jetson deployment before merge.
