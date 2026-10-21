# Public API Integration — letting a partner build their own site on our API

The Neo Chat API supports **server-to-server** third-party calls via API key
(format `nk_...`), with no need to go through our web login flow. A key is
bound to a **service account** (an ordinary user), so it's constrained by the
same RBAC as everyone else — role, factory access, document access — and can
be revoked instantly from the admin side.

```
Partner website (browser)
   │  (partner designs their own auth)
   ▼
Partner backend  ── Authorization: Bearer nk_xxx ──►  Neo Chat API (Jetson :8000)
```

> **Never embed the API key in browser code** — the key has the full
> privileges of its service account. Keep it server-side on the partner's
> end only, and proxy requests from their own front end.

## 1) Our side (admin on Jetson): issuing a key

1. Create one service account per partner, scoped to only what's needed:

```bash
curl -X POST https://spark-api.example.com/api/v1/admin/users \
  -H "Authorization: Bearer <ADMIN_JWT>" -H "Content-Type: application/json" \
  -d '{
    "email": "svc-partner@example.com",
    "full_name": "Partner X Service Account",
    "password": "<random-strong>",
    "role": "employee",
    "factory_access": [{"factory_id": "F-01", "access_level": "read"}]
  }'
```

2. Issue an API key for that user (the response includes the full `api_key`
   **once only** — the system stores only its SHA-256 hash):

```bash
curl -X POST https://spark-api.example.com/api/v1/admin/api-keys \
  -H "Authorization: Bearer <ADMIN_JWT>" -H "Content-Type: application/json" \
  -d '{"name": "partner-x-website", "user_id": "<USER_ID>", "expires_at": null}'
# → {"api_key": "nk_...", "key_prefix": "nk_xxxxxxxx", "key_id": "...", ...}
```

3. Manage it afterward:

```bash
curl -H "Authorization: Bearer <ADMIN_JWT>" https://.../api/v1/admin/api-keys          # list (prefix only)
curl -X POST -H "Authorization: Bearer <ADMIN_JWT>" https://.../api/v1/admin/api-keys/<KEY_ID>/revoke
curl -X DELETE -H "Authorization: Bearer <ADMIN_JWT>" https://.../api/v1/admin/api-keys/<KEY_ID>
```

Revocation takes effect immediately (the cache entry is cleared on revoke;
up to 60 seconds to propagate to other nodes). Deactivating a user
(`is_active=false`) also cuts off every key that user holds.

## 2) Partner side: calling the API

Use the key as a plain bearer token against any endpoint under `/api/v1` —
the full spec is at `/docs` (Swagger) or `/openapi.json`.

**Simple Q&A (no session, single JSON response):**

```bash
curl -X POST https://spark-api.example.com/api/v1/rag/query \
  -H "Authorization: Bearer nk_xxx" -H "Content-Type: application/json" \
  -d '{"question": "Servo Motor MC-001 is running abnormally hot, what should I do?", "filter": {"factory_id": "F-01"}}'
# → {"answer": "...", "sources": [...], "intent": "...", ...}
```

**Chat with a session + streaming (SSE):**

```bash
SESSION=$(curl -s -X POST https://.../api/v1/chat/sessions \
  -H "Authorization: Bearer nk_xxx" -H "Content-Type: application/json" \
  -d '{"factory_id": "F-01"}' | jq -r .session_id)

curl -N -X POST "https://.../api/v1/chat/${SESSION}/ask" \
  -H "Authorization: Bearer nk_xxx" -H "Content-Type: application/json" \
  -d '{"question": "How do I maintain MC-001?", "stream": true}'
```

An API key in the header works directly against the SSE route — **no stream
ticket needed** (tickets exist for browser `EventSource`, which can't set
custom headers).

**Node.js:**

```js
const res = await fetch("https://spark-api.example.com/api/v1/rag/query", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.NEO_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ question, filter: { factory_id: "F-01" } }),
});
const { answer, sources } = await res.json();
```

Every error uses the same envelope: `{"detail", "code", "trace_id", ...}` —
key-related codes: `api_key_invalid` / `api_key_revoked` / `api_key_expired`
/ `api_key_user_inactive` (HTTP 401)

## 3) Exposing the API outside the Jetson

Pick one:

| Route | Best for | How |
| --- | --- | --- |
| **Cloudflare Tunnel** (recommended) | partner is off-LAN, no port to open | `ops/cloudflared/config.example.yml` already has an ingress rule for `spark-api.*` → `127.0.0.1:8000` — follow the 6 steps in that file's comments for free HTTPS |
| **nginx on the LAN** | partner is on the same factory/VPN network | use `deploy/nginx/conf.d/spark.conf` (already has rate limiting + SSE passthrough) and point internal DNS at the Jetson |
| **Port forward + your own TLS** | you already have a public IP / reverse proxy | forward 443 → nginx → `api:8000`; never expose bare `:8000` without TLS |

Checklist before going live:

- `AUTH_REQUIRED=true` (already enforced in production — never disable)
- `CORS_ORIGINS` should list only our own web origin — partners call from
  their backend, so their origin never needs to be added
- `/metrics` stays LAN-only in the nginx config; `/docs`, `/redoc`, and
  `/openapi.json` are public (no auth) so partners can browse the live spec
- Issue a separate key per partner (give `name` a meaningful value) and set
  `expires_at` for anything temporary
- The global rate limit + concurrency middleware treats this like normal
  traffic; review usage via `last_used_at` on the list endpoint
