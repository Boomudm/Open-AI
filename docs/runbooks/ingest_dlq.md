# Ingest DLQ Runbook

Triage documents routed to **Dead Letter Queue (DLQ)** during ingestion.
Jobs with `status=dlq` require operator or admin action — they will not retry automatically.

---

## What is ingest DLQ?

When the ingestion pipeline hits a **permanent** failure (content policy block, trust gate,
quarantine under production lock, exhausted retries), the job moves to `dlq` instead of
`failed`. DLQ jobs are visible in:

- Admin ingest job list: `GET /api/v1/ingest/jobs?status=dlq`
- System-admin NOC metrics: `ingestion_error_rows`
- Prometheus: `spark_ingest_dlq_total`

Implementation: `src/spark/ingestion/job_reliability.py`

---

## Triage workflow

### 1. Identify DLQ jobs

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://spark.lan/api/v1/ingest/jobs?status=dlq&limit=50" | jq '.items[] | {job_id, doc_id, error_message, document_type}'
```

Or check Celery worker logs:

```bash
$ENV logs --tail=200 celery_worker | grep -i dlq
```

### 2. Classify reason

| Reason pattern | Typical cause | Action |
|----------------|---------------|--------|
| `policy_block` / trust hit | Blocked content, OCR trust, adversarial scan | Review source file; fix or reject upload |
| `quarantine` | Document flagged for manual review | Compliance review → release or delete |
| `config_hash` mismatch | Ingest config changed mid-job | Re-upload after config stabilizes |
| Parse / permanent parse error | Corrupt or unsupported file | Re-export PDF; try different format |

See reason codes: `src/spark/ingestion/reason_codes.py`

### 3. Resolve

| Resolution | Steps |
|------------|-------|
| **Re-upload fixed file** | Delete DLQ job + doc if needed; upload corrected source via `/upload` |
| **False positive** | Engineering adjusts trust/policy YAML; reingest after eval token if production lock active |
| **Accept reject** | Document stays out of RAG; notify uploader |

### 4. Verify queue clean

```bash
uv run python scripts/wait_ingest_idle.py --timeout 60
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://spark.lan/api/v1/ingest/jobs?status=dlq" | jq '.total'
# Expect 0 before cutover
```

---

## Notifications

DLQ events may trigger operator notifications (`ingest_dlq` event type).
Configure notification channels in factory admin settings.

---

## Prevention (production)

Before pilot cutover:

1. Run ingest preflight on sample docs: `POST /api/v1/ingest/preflight`
2. Complete full reingest without DLQ spike
3. Monitor `spark_ingest_dlq_total` during 72h soak — see
   [factory_pilot_cutover.md](./factory_pilot_cutover.md)

---

## Escalation

| Severity | When | Who |
|----------|------|-----|
| SEV-2 | DLQ rate > 5% of daily uploads | Plant IT + engineering |
| SEV-1 | Safety/policy block on critical SOP | Compliance + engineering |

Postmortem template: [postmortem/template.md](../postmortem/template.md)

---

## Related

- [operations-guide.md](../operations-guide.md) — Celery logs, disk space
- [runbook.md](../runbook.md) — daily checklist
- [import_spine_v2.md](../architecture/import_spine_v2.md) — pipeline design
