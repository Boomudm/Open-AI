# Jetson AGX Orin — Compute Node + Mac Thin Client

Move the heavy work (embed bge-m3, rerank, ingest, DB, Qdrant) to the Jetson.
The Mac only runs a browser (or dev tools on the Mac, if you want).

**Mode currently deployed:** the Jetson runs **both backend + frontend**

```
Jetson Orin                         Gateway
:8000 API + Celery                  api.kcalsion.com
:3000 Next.js (npm run dev)         qwen3.6:35b (LLM only)
postgres/redis/qdrant/minio
bge-m3 + rerank on CUDA
```

**Access it at:** http://10.11.98.156:3000 — from any machine that can SSH to
the Jetson (same LAN)

**Not on the same Wi-Fi (Mac):** tunnel just port 3000

```bash
ssh -L 3000:localhost:3000 jetson@10.11.98.156
# then open http://localhost:3000
```

**Mac thin-client mode (optional):** Next.js on the Mac proxies to `:8000`
on the Jetson — see below

```
Mac (display)                Jetson Orin (compute)
:3000 Next.js  ──proxy──►  :8000 API + Celery
```

**Expose the API to a third party (for them to build their own site):**
issue an API key `nk_...` via `/api/v1/admin/api-keys`, then expose `:8000`
through a Cloudflare Tunnel or nginx — see
[docs/public-api-integration.md](../../docs/public-api-integration.md)

---

## What you have to do yourself (can't be automated)

| # | Where | Details |
|---|------|------------|
| 1 | Jetson | Connect a display/keyboard or SSH in, plug in LAN (Wi-Fi/Ethernet) |
| 2 | Jetson | Flash **JetPack** (Ubuntu) if not already installed — [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) |
| 3 | Jetson | Find its **LAN IP**, e.g. `192.168.1.50` (`hostname -I`) |
| 4 | Jetson | Clone the repo: `git clone <repo-url> && cd spark` (or `scp` from the Mac) |
| 5 | Jetson | Run `sudo ./scripts/jetson/install_prereqs.sh`, then **log out/in** if you were just added to the docker group |
| 6 | Jetson | Edit `.env` and set `OLLAMA_API_KEY` (the existing gateway key) |
| 7 | Mac | Edit `web/.env.local` and set `SPARK_API_PROXY_TARGET=http://<JETSON_IP>:8000` |
| 8 | Both | Confirm the Jetson can reach the gateway (`curl -I https://api.kcalsion.com`) |

---

## What the scripts do for you (run in order)

### On the Jetson

```bash
cd ~/spark
chmod +x scripts/jetson/*.sh scripts/mac_dev_thin.sh

# first time only
sudo ./scripts/jetson/install_prereqs.sh
# log out/in if needed

./scripts/jetson/bootstrap_compute.sh    # infra + venv + DB + PyTorch CUDA
./scripts/jetson/start_compute.sh        # API :8000 + Celery (foreground)

# health check
./scripts/jetson/status_compute.sh
```

Check the boot log for `sentence_transformer_load` **`device=cuda`** (not
`cpu`).

### On the Mac

```bash
cd ~/spark
cp web/.env.mac-thin.example web/.env.local
# set SPARK_API_PROXY_TARGET=http://<JETSON_IP>:8000

./scripts/mac_dev_thin.sh    # opens http://127.0.0.1:3000

# stop Docker infra on the Mac if you no longer need it (saves RAM)
docker compose down
```

Login: `admin` / `changeme` (if freshly seeded)

---

## Migrating data from the Mac (if documents are already ingested)

**Mac:**
```bash
./scripts/jetson/migrate_export_mac.sh
scp -r deploy/jetson/migration_bundle user@JETSON_IP:~/spark/deploy/jetson/
```

**Jetson:**
```bash
./scripts/jetson/migrate_import_jetson.sh
./scripts/jetson/start_compute.sh
```

Note: the Postgres dump does not include Qdrant vectors — if a question
comes back with no documents found, **re-ingest** on the Jetson, or copy the
`spark_qdrant_data` Docker volume over from the Mac.

---

## Starting fresh with demo data (no migration from the Mac)

```bash
# on the Jetson, after bootstrap
source .venv/bin/activate
python scripts/seed_customer_demo.py --reset --ingest
```

---

## Quick troubleshooting

| Symptom | Fix |
|--------|-----|
| Mac UI times out | check `curl http://JETSON_IP:8000/healthz` from the Mac — or use the SSH tunnel (below) |
| `device=cpu` in the log | re-run `./scripts/jetson/install_pytorch.sh` |
| OOM on the 32GB Orin | lower `CELERY_CONCURRENCY=1`, close other apps on the Jetson |
| Chat returns 401 / bounces to login on ask | production requires a **stream ticket** — sync `streams.ts` + the chat/ingest stream hooks from the Mac, or disable `require_ticket_for_sse` in dev |
| Bounced after login / "session expired" | `JWT_SECRET` in **`web/.env.local` (Mac)** must match the Jetson's `.env` — Next.js verifies the cookie with this secret; after fixing it, **restart `npm run dev`** |
| Gateway 401 | set `OLLAMA_API_KEY` in the Jetson's `.env` |
| CORS error | don't set `NEXT_PUBLIC_API_URL` on the Mac — use the proxy only |

### Mac can't reach the Jetson's `:8000` directly — use an SSH tunnel

**Terminal 1 (leave open):**
```bash
chmod +x scripts/jetson/ssh_tunnel_mac.sh
JETSON_USER=jetson JETSON_HOST=10.11.98.156 ./scripts/jetson/ssh_tunnel_mac.sh
curl http://127.0.0.1:8000/healthz   # should return 200
```

**Terminal 2:**
```bash
cd web
cp .env.mac-tunnel.example .env.local
# set JWT_SECRET to match the Jetson: ssh jetson@HOST 'grep ^JWT_SECRET= .env'
npm run dev
```

The Next.js proxy goes to `127.0.0.1:8000` on the Mac → tunnel → Jetson — no
need to open firewall port 8000 to the whole LAN.

```bash
# or the direct command (the Jetson user is jetson)
ssh -L 8000:localhost:8000 jetson@10.11.98.156
```

---

## Syncing code from Mac → Jetson

Backend fixes were made on the Jetson (reingest endpoint, rescue task, PDF
spacing, progress %). **The frontend on the Jetson is still the old
source** until it pulls the fixes from the Mac.

### `web` files that need to be on the Jetson (from the Mac)

| File | What it does |
|------|--------|
| `web/lib/api/streams.ts` | `mintStreamTicket()` for SSE in production |
| `web/lib/api/chat.ts` | chat stream + attachments using `?ticket=` |
| `web/lib/chat/stream-consumer.ts` | chat SSE using the ticket |
| `web/hooks/useIngestJobStream.ts` | ingest job SSE using the ticket (no localStorage) |
| `web/lib/api/ingest.ts` | `reingestDocument()` |
| `web/components/documents/ReingestDocumentButton.tsx` | Re-ingest button on the Documents page |
| `web/components/documents/DocumentRow.tsx` | places the Re-ingest button |

### How to sync

**Recommended — git (after commit + push from the Mac):**

```bash
# on the Jetson
cd /mnt/nvme-data/spark-1   # or wherever the repo lives on the Jetson
git pull origin develop
cd web && npm install   # if package.json changed
# restart npm run dev on the Jetson (Ctrl+C then npm run dev)
```

**Alternative — rsync from the Mac:**

```bash
rsync -avz --exclude node_modules --exclude .next \
  ~/spark-2/web/ jetson@10.11.98.156:/mnt/nvme-data/spark-1/web/
```

After syncing the frontend, the Jetson must **restart `npm run dev`**
(Next.js reads env vars at start).

### Verify after syncing

- Login doesn't bounce the session (`JWT_SECRET` in `web/.env.local` on the
  Jetson must match the root `.env`)
- Chat can be asked (stream ticket works)
- Documents → Re-ingest button appears + the ingest job stream shows progress

---

## Getting stuck on Mac but running on the Jetson — no manual sync needed

If you edit a file on the Mac and the Jetson **doesn't know about it** (the
API/Celery read code that lives on the Jetson), there are two approaches:

### Recommended — VS Code / Cursor Remote SSH

Edit on the Mac, but the real file lives on the Jetson — **no duplication,
no delay**

1. Install the **Remote - SSH** extension (VS Code or Cursor)
2. `Cmd+Shift+P` → **Remote-SSH: Connect to Host**
3. `jetson@10.11.98.156`
4. Open the folder, e.g. `/mnt/nvme-data/spark-1` (or wherever the repo
   lives on the Jetson)
5. The terminal in the editor runs directly on the Jetson
   (`start_compute.sh`, tests, logs)

The Mac still only runs the **frontend** (`web/` + tunnel) as before —
backend edits go through Remote SSH.

### Alternative — rsync auto-sync (editing the repo on the Mac for real)

```bash
brew install fswatch

fswatch -o ~/path/to/spark-1 | xargs -I{} rsync -avz \
  --exclude node_modules --exclude .git --exclude .next \
  ~/path/to/spark-1/ jetson@10.11.98.156:/mnt/nvme-data/spark-1/
```

The API/Celery on the Jetson must be restarted after syncing Python code —
Remote SSH is simpler and won't miss a file.

---

## Related files

| File | Purpose |
|------|--------|
| `deploy/jetson/.env.jetson.example` | `.env` template for the Jetson |
| `scripts/jetson/bootstrap_compute.sh` | first-time install |
| `scripts/jetson/start_compute.sh` | run API + Celery |
| `scripts/mac_dev_thin.sh` | Mac runs only the web frontend |
| `web/.env.mac-thin.example` | proxy to the Jetson |
