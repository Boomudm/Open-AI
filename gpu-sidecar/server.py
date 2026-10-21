"""GPU inference sidecar — bge-m3 dense embeddings + bge-reranker-v2-m3 rerank.

Runs on the host's Python 3.8 + JetPack CUDA PyTorch (the only torch build with
working GPU on this JetPack-5.1 / CUDA-11.4 device). The main Spark app (Python
3.12, CPU-only torch in its container) calls this over HTTP and falls back to its
own in-process CPU models if this service is unreachable — so the app never hard-
depends on the sidecar.

Parity contract (verified 2026-07): /embed returns the SAME vectors the app's
SentenceTransformerEmbeddings produces (cosine 1.0000 vs the CPU path), so the
3k+ vectors already indexed in Qdrant stay compatible. /rerank returns RAW
CrossEncoder logits; the app applies its own sigmoid, identical to its CPU path.
"""

import os
import threading
from typing import List, Optional

# Load models from the local copied cache only — never reach out to HF Hub.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sentence_transformers import CrossEncoder, SentenceTransformer  # noqa: E402

EMBED_MODEL = os.environ.get("SIDECAR_EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("SIDECAR_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_MAXLEN = int(os.environ.get("SIDECAR_RERANK_MAXLEN", "1024"))
EMBED_BATCH = int(os.environ.get("SIDECAR_EMBED_BATCH", "32"))
RERANK_BATCH = int(os.environ.get("SIDECAR_RERANK_BATCH", "64"))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# Half precision for rerank only. Measured on this Orin (16 real corpus chunks,
# 0.8-3.8k chars, 4 Thai/English queries): 5618ms -> 1507ms (3.7x) with Spearman
# 1.00000 against the fp32 scores and identical top-1/top-3 — max logit delta
# 5.5e-4. Rerank scores are ephemeral (recomputed per query), so precision drift
# cannot corrupt stored state. The EMBEDDER deliberately stays fp32: its vectors
# are persisted in Qdrant and must keep bit-parity with the 5.8k already-indexed
# points (see the parity contract above); query embeds are Redis-cached anyway,
# so there is no latency to win there.
RERANK_FP16 = os.environ.get("SIDECAR_RERANK_FP16", "1") == "1" and DEVICE == "cuda"

# Single GPU, single CUDA context — serialize model calls. Each call is sub-second
# so lock contention is negligible; this just prevents concurrent-request races.
_gpu_lock = threading.Lock()

app = FastAPI(title="spark-gpu-sidecar")
_embedder: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None


@app.on_event("startup")
def _startup() -> None:
    global _embedder, _reranker
    _embedder = SentenceTransformer(EMBED_MODEL, device=DEVICE)
    _reranker = CrossEncoder(RERANK_MODEL, max_length=RERANK_MAXLEN, device=DEVICE)
    if RERANK_FP16:
        _reranker.model.half()
    # Warm both models so the first real request isn't paying cold-start cost.
    with _gpu_lock:
        _embedder.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
        _reranker.predict([["warmup", "warmup"]], show_progress_bar=False)


class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True


class RerankRequest(BaseModel):
    query: str
    texts: List[str]


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": _embedder is not None and _reranker is not None,
        "device": DEVICE,
        "embed_model": EMBED_MODEL,
        "rerank_model": RERANK_MODEL,
        "rerank_dtype": "fp16" if RERANK_FP16 else "fp32",
    }


@app.post("/embed")
def embed(req: EmbedRequest) -> dict:
    if not req.texts:
        return {"vectors": []}
    assert _embedder is not None
    with _gpu_lock:
        vectors = _embedder.encode(
            req.texts,
            normalize_embeddings=req.normalize,
            convert_to_numpy=True,
            batch_size=EMBED_BATCH,
            show_progress_bar=False,
        )
    return {"vectors": [v.tolist() for v in vectors]}


@app.post("/rerank")
def rerank(req: RerankRequest) -> dict:
    if not req.texts:
        return {"scores": []}
    assert _reranker is not None
    pairs = [[req.query, t] for t in req.texts]
    with _gpu_lock:
        raw = _reranker.predict(pairs, batch_size=RERANK_BATCH, show_progress_bar=False)
    # RAW logits — the caller applies its own sigmoid to match its CPU path.
    return {"scores": [float(x) for x in raw]}
