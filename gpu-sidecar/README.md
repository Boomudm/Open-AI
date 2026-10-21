# Spark GPU inference sidecar

A tiny HTTP service that runs the **dense embedder (bge-m3)** and **cross-encoder
reranker (bge-reranker-v2-m3)** on the Jetson **GPU**, so the main app (which runs
in a Python 3.12 container with CPU-only torch) can offload them.

## Why this exists

This is a JetPack 5.1 / CUDA 11.4 device. The only PyTorch build with working GPU
here is the JetPack one for **Python 3.8** — and the app requires Python ≥3.11, so
GPU torch cannot live in the app container. This sidecar bridges that gap:

- runs on the host's Python 3.8 + JetPack CUDA torch (GPU works),
- the app calls it over HTTP and **falls back to its in-process CPU models** on
  any failure (so the app never hard-depends on it),
- `/embed` returns vectors byte-for-byte equivalent to the app's CPU embedder
  (verified cosine 1.0), so already-indexed Qdrant vectors stay compatible.

Measured on this box: reranking 34 real chunks went from ~20–80 s (CPU, timing
out) to ~0.6 s (GPU); query embedding 340 ms → 66 ms.

## Files (tracked)

- `server.py` — FastAPI service: `/embed`, `/rerank`, `/healthz`.
- `start.sh` — launcher used by systemd and for manual runs.
- `spark-gpu-sidecar.service` — systemd unit (install with sudo, see below).
- `.gitignore` — excludes the host-local venv + model cache.

## One-time setup on a fresh host

```bash
cd /mnt/nvme-data/spark-1/gpu-sidecar

# 1. venv that REUSES the host's JetPack GPU torch (do not reinstall torch)
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -c constraints.txt --prefer-binary \
    fastapi "uvicorn[standard]" "sentence-transformers==2.7.0"
#   constraints.txt pins: numpy<2, torch==2.2.0, huggingface_hub==0.24.6,
#   transformers==4.40.2  (keeps the host GPU torch + avoids the hf_xet Rust build)

# 2. model cache (copy from the app container, or let HF download once)
mkdir -p hf-cache/hub
docker cp spark_api:/app/.cache/huggingface/hub/models--BAAI--bge-m3           hf-cache/hub/
docker cp spark_api:/app/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3 hf-cache/hub/

# 3. install + enable the service (survives reboot)
sudo cp spark-gpu-sidecar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spark-gpu-sidecar.service
```

## Wiring (already in the app)

The app reads `GPU_SIDECAR_URL` (set in `docker-compose.dev-app.yml` to
`http://host.docker.internal:8137`). Clear it and recreate the containers to fall
back to pure-CPU behavior — fully reversible, no code change.

## Health

```bash
curl http://localhost:8137/healthz   # {"ok":true,"device":"cuda",...}
systemctl status spark-gpu-sidecar
```

---

See also: [../README.md](../README.md) · [../docs/HANDOVER.md](../docs/HANDOVER.md) · [../docs/operations-guide.md](../docs/operations-guide.md)
