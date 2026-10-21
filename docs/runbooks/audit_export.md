# Audit Export Runbook

Compliance bundle export for retrieval logs and WORM audit events.
API: `GET /api/v1/audit/export` · Role: **compliance_officer** (or admin with factory scope).

---

## When to use

- Regulatory audit or internal compliance review
- Post-incident evidence collection (scope broadening, safety refusal, quarantine)
- Scheduled quarterly export archive

**Not for** routine operator support — use admin retrieval CSV at
`GET /api/v1/admin/audit/export` (admin role, CSV only).

---

## Prerequisites

| Item | Setting |
|------|---------|
| Role | User has `compliance_officer` in JWT roles |
| HMAC secret | `AUDIT_EXPORT_HMAC_SECRET` in production `.env` |
| Rate limit | Default 10 exports/user/hour (Redis) |
| Classification filter | Optional — see `configs/compliance/data_classification.yaml` |

---

## Export procedure

```bash
TOKEN=$(curl -s -X POST http://spark.lan/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<compliance_user>","password":"***"}' | jq -r .token)

curl -s "http://spark.lan/api/v1/audit/export?factory_id=F-01&days=90" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Response includes:

- `retrieval_log` — redacted RAG retrieval rows
- `worm_audit` — hash-chained immutable events
- `chain_valid` — WORM chain integrity check
- `download_token` — signed token (HMAC, time-limited)

Optional query params:

| Param | Purpose |
|-------|---------|
| `factory_id` | Scope to one factory (required for non-admin) |
| `days` | Lookback 1–365 (capped by `max_bundle_days`) |
| `classification_level` | Filter WORM events by data classification |

---

## Validation

1. Confirm `chain_valid: true` — if false, escalate to engineering (possible tamper or migration issue).
2. Store bundle in approved compliance storage — **not** in git or public ticket systems.
3. Record export in client audit log (who, when, factory, days).

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| 403 compliance_officer | Assign role in `/admin` |
| 429 rate limit | Wait or request limit bump for bulk export window |
| Empty worm_audit | WORM sink may be disabled in dev; check `APP_ENV` and migrations |
| chain_valid false | Do not use bundle for legal evidence until engineering investigates |

---

## Security

- Never attach export JSON to public GitHub issues
- Rotate `AUDIT_EXPORT_HMAC_SECRET` on compromise
- Report leaks via [SECURITY.md](../../SECURITY.md)

---

## Related

- [HANDOVER.md](../HANDOVER.md) — `AUDIT_EXPORT_HMAC_SECRET` in secrets template
- [factory_pilot_cutover.md](./factory_pilot_cutover.md) — go-live gates
