## Summary

<!-- What changed and why? Link issues: closes #123 -->

## Remediation phase (if applicable)

- [ ] Phase N — see `configs/remediation/phase_gates_v3.yaml` and `docs/runbooks/cutover_checklist_v3.md`

## Eval (RAG / safety changes)

- [ ] `configs/eval/baseline_ci.yaml` green (`--deterministic-rag`)
- [ ] `configs/eval/adversarial.yaml` green (`--require-answer-path`)
- [ ] `scripts/remediation_phase_gate.py --phase N` when touching gated phase

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature
- [ ] Refactor / chore (no user-visible change)
- [ ] Documentation only
- [ ] CI / security / Dependabot

## Test plan

<!-- How did you verify this? Include commands run. -->

- [ ] `uv run ruff check src tests` (Python touched)
- [ ] `uv run pytest tests/ -q --tb=short` (Python touched)
- [ ] `cd web && npx tsc --noEmit && npm run lint && npm test` (web touched)
- [ ] `npm run test:e2e` (web UX / routing touched)
- [ ] Manual verification described below

**Manual steps:**

1.
2.

## Documentation

- [ ] Updated `CHANGELOG.md` under `[unreleased]` (user-visible / API changes)
- [ ] Updated `README.md` or `docs/` if setup or behavior changed
- [ ] No documentation updates needed

## Security & data

- [ ] No secrets, `.env` values, or plant document samples in this PR
- [ ] Auth / RBAC / RAG filter changes reviewed for cross-factory leakage
- [ ] N/A — no security-sensitive paths touched

## Screenshots / recordings

<!-- UI changes: before/after screenshots or short clip -->

## Notes for reviewers

<!-- Optional: migration steps, feature flags, rollout plan -->
