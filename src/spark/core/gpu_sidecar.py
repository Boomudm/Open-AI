"""Client for the optional GPU inference sidecar (dense embed + rerank).

The sidecar runs on the host's Python 3.8 + JetPack CUDA PyTorch — the only
torch build with working GPU on this JetPack-5.1 device — and the app (Python
3.12, CPU-only torch in its container) calls it over HTTP. Every function here
returns ``None`` on any failure (sidecar unset, unreachable, timeout, bad
response) so callers fall back to their in-process CPU models. The app therefore
never hard-depends on the sidecar: turn it off by clearing GPU_SIDECAR_URL and
the app reverts to pure-CPU behavior with no code change.

Sync helpers are used from embedder / sync CE paths inside thread-pool workers.
Async helpers are used from ``CrossEncoderReranker.score_pairs_async`` so rerank
never queues behind embed/sparse work on the default executor.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Sequence

import httpx

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

_client: httpx.Client | None = None
_client_lock = threading.Lock()
_async_client: httpx.AsyncClient | None = None
_async_client_lock = asyncio.Lock()


def sidecar_enabled() -> bool:
    return bool((settings.gpu_sidecar_url or "").strip())


def _sidecar_timeout() -> httpx.Timeout:
    total = float(getattr(settings, "gpu_sidecar_timeout_sec", 15.0) or 15.0)
    connect = min(5.0, total)
    return httpx.Timeout(total, connect=connect)


def _sidecar_base_url() -> str:
    return (settings.gpu_sidecar_url or "").strip().rstrip("/")


def _get_client() -> httpx.Client | None:
    global _client
    base = _sidecar_base_url()
    if not base:
        return None
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(base_url=base, timeout=_sidecar_timeout())
    return _client


async def _get_async_client() -> httpx.AsyncClient | None:
    global _async_client
    base = _sidecar_base_url()
    if not base:
        return None
    if _async_client is None:
        async with _async_client_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(base_url=base, timeout=_sidecar_timeout())
    return _async_client


def reset_client() -> None:
    """Drop the cached client (e.g. after config reload or in Celery workers)."""
    global _client, _async_client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
        _client = None
    _async_client = None


def embed_texts(texts: Sequence[str], *, normalize: bool = True) -> list[list[float]] | None:
    """Dense-embed via the sidecar. Returns None to signal 'fall back to CPU'."""
    if not texts:
        return []
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.post("/embed", json={"texts": list(texts), "normalize": normalize})
        resp.raise_for_status()
        vectors = resp.json().get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            log.warning("gpu_sidecar_embed_bad_response", got=type(vectors).__name__)
            return None
        return [[float(x) for x in vec] for vec in vectors]
    except Exception as exc:
        log.warning("gpu_sidecar_embed_failed", error=str(exc)[:200], fallback="cpu")
        return None


def rerank_scores(query: str, texts: Sequence[str]) -> list[float] | None:
    """Raw cross-encoder logits via the sidecar. Caller applies its own sigmoid.

    Returns None to signal 'fall back to CPU'.
    """
    if not texts:
        return []
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.post("/rerank", json={"query": query, "texts": list(texts)})
        resp.raise_for_status()
        scores = resp.json().get("scores")
        if not isinstance(scores, list) or len(scores) != len(texts):
            log.warning("gpu_sidecar_rerank_bad_response", got=type(scores).__name__)
            return None
        return [float(x) for x in scores]
    except Exception as exc:
        log.warning("gpu_sidecar_rerank_failed", error=str(exc)[:200], fallback="cpu")
        return None


async def rerank_scores_async(query: str, texts: Sequence[str]) -> list[float] | None:
    """Async sidecar rerank — avoids default thread-pool queueing during RAG."""
    if not texts:
        return []
    client = await _get_async_client()
    if client is None:
        return None
    try:
        resp = await client.post("/rerank", json={"query": query, "texts": list(texts)})
        resp.raise_for_status()
        scores = resp.json().get("scores")
        if not isinstance(scores, list) or len(scores) != len(texts):
            log.warning("gpu_sidecar_rerank_bad_response", got=type(scores).__name__)
            return None
        return [float(x) for x in scores]
    except Exception as exc:
        log.warning("gpu_sidecar_rerank_failed", error=str(exc)[:200], fallback="cpu")
        return None
