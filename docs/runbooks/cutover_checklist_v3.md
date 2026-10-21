# Cutover Checklist (v3)

Production cutover checklist for factory pilots. Canonical runbook:
[factory_pilot_cutover.md](./factory_pilot_cutover.md).

> Detailed remediation blueprints (`remediation_blueprint_v3/`, v2 archive) are
> **local-only** — not published on GitHub. Phase gate config lives in
> `configs/remediation/phase_gates_v3.yaml`.

## Guiding principles

1. Every change must pass its phase gate contract tests before merge.
2. No runtime behavior change without eval gate validation.
3. All payload fields are governed by the RAG payload contract.
4. `production_lock_v3` governs eval-gated deployments.

## Prerequisites

- [ ] `production_lock_v3` enabled for target scope
- [ ] `full_reingest_v2_sparse.py` completed successfully
- [ ] All phase gates (0–16) green
- [ ] `go_live_preflight.sh --v3 --strict` passes

## Cutover steps

- [ ] Execute sparse reindex for pilot factories
- [ ] Run `handover_validate.py` smoke after reingest
- [ ] Monitor 72h soak period (Grafana RAG SLO + ingest alerts)
- [ ] Validate retrieval quality metrics
- [ ] Sign off: [`docs/runbooks/templates/pilot_soak_signoff.md`](./templates/pilot_soak_signoff.md)

## Rollback

- [ ] Run `rollback_generation_pin.py`
- [ ] Disable `production_lock_v3` for affected factory
- [ ] Confirm rollback via eval suite
- [ ] File postmortem: [postmortem/template.md](../postmortem/template.md)
