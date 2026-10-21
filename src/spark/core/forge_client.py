"""HTTP client for ForgeNode (forge.kcalsion.com) — embed, rerank, health, models.

Priority over the local GPU sidecar when ``FORGE_BASE_URL`` is set: offloads dense
embed + rerank from the Jetson container so bge-m3 / cross-encoder models do not
need to load in-process.

Falls back to ``None`` on any failure so callers can chain gpu_sidecar → local CPU.
"""

from __future__ import annotations

import asyncio
import math
import threading
from typing import Any, Sequence

import httpx

from spark.core.config import settings
from spark.core.llm_client import openai_gateway_headers
from spark.core.logging import get_logger

log = get_logger(__name__)

_sync_client: httpx.Client | None = None
_sync_lock = threading.Lock()
_async_client: httpx.AsyncClient | None = None
_async_lock = asyncio.Lock()


def forge_enabled() -> bool:
    return bool((settings.forge_base_url or "").strip())


def forge_rerank_active() -> bool:
    """True when rerank requests should go to Forge (env or profile flag)."""
    if not forge_enabled():
        return False
    if settings.forge_rerank_enabled:
        return True
    try:
        from spark.core.llm_profile import load_llm_profile

        profile = load_llm_profile()
        reranker = profile.get("reranker")
        if isinstance(reranker, dict):
            backend = str(reranker.get("backend") or "").strip().lower()
            if backend == "forge":
                return True
    except Exception:
        pass
    return settings.forge_rerank_enabled


def _base_url() -> str:
    return (settings.forge_base_url or "").strip().rstrip("/")


def _api_v1_base() -> str:
    base = _base_url()
    return base if base.endswith("/v1") else f"{base}/v1"


def _chat_api_key() -> str:
    return (
        (settings.forge_api_key or "").strip()
        or (settings.ollama_api_key or "").strip()
        or "spark-local"
    )


def _embed_api_key() -> str:
    return (
        (settings.forge_embed_api_key or "").strip()
        or (settings.ollama_embed_api_key or "").strip()
        or _chat_api_key()
    )


def _rerank_api_key() -> str:
    return (
        (settings.forge_rerank_api_key or "").strip()
        or _embed_api_key()
    )


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = dict(openai_gateway_headers())
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _timeout() -> httpx.Timeout:
    total = float(getattr(settings, "forge_timeout_sec", 30.0) or 30.0)
    connect = min(5.0, total)
    return httpx.Timeout(total, connect=connect)


def _get_sync_client() -> httpx.Client | None:
    global _sync_client
    if not forge_enabled():
        return None
    if _sync_client is None:
        with _sync_lock:
            if _sync_client is None:
                _sync_client = httpx.Client(base_url=_base_url(), timeout=_timeout())
    return _sync_client


async def _get_async_client() -> httpx.AsyncClient | None:
    global _async_client
    if not forge_enabled():
        return None
    if _async_client is None:
        async with _async_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(base_url=_base_url(), timeout=_timeout())
    return _async_client


def reset_client() -> None:
    global _sync_client, _async_client
    with _sync_lock:
        if _sync_client is not None:
            try:
                _sync_client.close()
            except Exception:
                pass
        _sync_client = None
    _async_client = None


def _normalize_vectors(raw: Any, expected: int) -> list[list[float]] | None:
    if not isinstance(raw, list) or len(raw) != expected:
        return None
    out: list[list[float]] = []
    for item in raw:
        if isinstance(item, dict) and "embedding" in item:
            vec = item["embedding"]
        else:
            vec = item
        if not isinstance(vec, list) or not vec:
            return None
        out.append([float(x) for x in vec])
    return out


def _parse_rerank_scores(payload: Any, n_docs: int) -> list[float] | None:
    """Map Forge /v1/rerank JSON to per-document scores in input order (0–1)."""
    if not isinstance(payload, dict):
        return None

    results = payload.get("results")
    if isinstance(results, list) and results:
        scores = [0.0] * n_docs
        for row in results:
            if not isinstance(row, dict):
                continue
            idx = row.get("index")
            if idx is None and "document" in row:
                # Some APIs omit index when return_documents=true — match by text later
                continue
            try:
                pos = int(idx)
            except (TypeError, ValueError):
                continue
            if not (0 <= pos < n_docs):
                continue
            raw_score = row.get("relevance_score", row.get("score"))
            if raw_score is None:
                continue
            scores[pos] = _coerce_unit_score(float(raw_score))

        if any(s > 0 for s in scores):
            return scores

    # Flat list of scores
    if isinstance(payload.get("scores"), list):
        scores_raw = payload["scores"]
        if len(scores_raw) == n_docs:
            return [_coerce_unit_score(float(s)) for s in scores_raw]

    return None


def _coerce_unit_score(value: float) -> float:
    """Normalize rerank outputs to [0, 1] (logits vs probability)."""
    if not math.isfinite(value):
        return 0.0
    if 0.0 <= value <= 1.0:
        return value
    # Logit-style fallback (sidecar-compatible)
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def embed_texts(texts: Sequence[str], *, normalize: bool = True) -> list[list[float]] | None:
    if not texts:
        return []
    client = _get_sync_client()
    if client is None:
        return None
    model = (settings.forge_embed_model or "bge-m3").strip()
    try:
        resp = client.post(
            f"{_api_v1_base()}/embeddings",
            headers=_auth_headers(_embed_api_key()),
            json={"model": model, "input": list(texts)},
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, list):
            # OpenAI format: [{embedding: [...], index: 0}, ...]
            ordered = sorted(
                (row for row in data if isinstance(row, dict)),
                key=lambda r: int(r.get("index", 0)),
            )
            vectors = _normalize_vectors(
                [row.get("embedding") for row in ordered],
                len(texts),
            )
        else:
            vectors = _normalize_vectors(body.get("vectors") if isinstance(body, dict) else None, len(texts))
        if vectors is None:
            log.warning("forge_embed_bad_response", model=model)
            return None
        if normalize:
            vectors = [_l2_normalize(v) for v in vectors]
        log.debug("forge_embed_ok", count=len(texts), model=model)
        return vectors
    except Exception as exc:
        log.warning("forge_embed_failed", error=str(exc)[:200], fallback="next")
        return None


async def embed_texts_async(texts: Sequence[str], *, normalize: bool = True) -> list[list[float]] | None:
    if not texts:
        return []
    client = await _get_async_client()
    if client is None:
        return None
    model = (settings.forge_embed_model or "bge-m3").strip()
    try:
        resp = await client.post(
            f"{_api_v1_base()}/embeddings",
            headers=_auth_headers(_embed_api_key()),
            json={"model": model, "input": list(texts)},
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, list):
            ordered = sorted(
                (row for row in data if isinstance(row, dict)),
                key=lambda r: int(r.get("index", 0)),
            )
            vectors = _normalize_vectors(
                [row.get("embedding") for row in ordered],
                len(texts),
            )
        else:
            vectors = _normalize_vectors(body.get("vectors") if isinstance(body, dict) else None, len(texts))
        if vectors is None:
            log.warning("forge_embed_bad_response", model=model)
            return None
        if normalize:
            vectors = [_l2_normalize(v) for v in vectors]
        return vectors
    except Exception as exc:
        log.warning("forge_embed_async_failed", error=str(exc)[:200], fallback="next")
        return None


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


def rerank_scores(query: str, texts: Sequence[str]) -> list[float] | None:
    if not texts:
        return []
    if not forge_rerank_active():
        return None
    client = _get_sync_client()
    if client is None:
        return None
    model = (settings.forge_rerank_model or "Qwen/Qwen3-Reranker-0.6B").strip()
    try:
        resp = client.post(
            f"{_api_v1_base()}/rerank",
            headers=_auth_headers(_rerank_api_key()),
            json={
                "model": model,
                "query": query,
                "documents": list(texts),
                "top_n": len(texts),
                "return_documents": False,
            },
        )
        resp.raise_for_status()
        scores = _parse_rerank_scores(resp.json(), len(texts))
        if scores is None:
            log.warning("forge_rerank_bad_response", model=model)
            return None
        log.debug("forge_rerank_ok", pairs=len(texts), model=model)
        return scores
    except Exception as exc:
        log.warning("forge_rerank_failed", error=str(exc)[:200], fallback="next")
        return None


async def rerank_scores_async(query: str, texts: Sequence[str]) -> list[float] | None:
    if not texts:
        return []
    if not forge_rerank_active():
        return None
    client = await _get_async_client()
    if client is None:
        return None
    model = (settings.forge_rerank_model or "Qwen/Qwen3-Reranker-0.6B").strip()
    # Bound the rerank call independently of the 30s client budget: if the remote
    # reranker hangs, fail fast so the caller's fallback chain can reach the
    # local sidecar within the retrieval deadline instead of degrading to a
    # zero-score fusion rank (which surfaces as a false "no data" answer).
    rerank_timeout = float(getattr(settings, "forge_rerank_timeout_sec", 4.0) or 4.0)
    try:
        resp = await client.post(
            f"{_api_v1_base()}/rerank",
            headers=_auth_headers(_rerank_api_key()),
            json={
                "model": model,
                "query": query,
                "documents": list(texts),
                "top_n": len(texts),
                "return_documents": False,
            },
            timeout=rerank_timeout,
        )
        resp.raise_for_status()
        scores = _parse_rerank_scores(resp.json(), len(texts))
        if scores is None:
            log.warning("forge_rerank_bad_response", model=model)
            return None
        return scores
    except Exception as exc:
        log.warning("forge_rerank_async_failed", error=str(exc)[:200], fallback="next")
        return None


async def fetch_forge_status() -> dict[str, Any]:
    """Health + /v1/models probe for NOC and startup checks."""
    if not forge_enabled():
        return {"enabled": False, "ok": False}

    base = _base_url()
    out: dict[str, Any] = {
        "enabled": True,
        "base_url": base,
        "embed_model": settings.forge_embed_model,
        "rerank_model": settings.forge_rerank_model,
        "ok": False,
    }
    client = await _get_async_client()
    if client is None:
        out["error"] = "client_unavailable"
        return out

    try:
        health_resp = await client.get("/health")
        out["health"] = {
            "ok": health_resp.status_code < 500,
            "status": health_resp.status_code,
            "body": health_resp.text[:200],
        }
    except Exception as exc:
        out["health"] = {"ok": False, "error": str(exc)[:120]}

    models_ok = False
    model_ids: list[str] = []
    try:
        models_resp = await client.get(
            f"{_api_v1_base()}/models",
            headers=_auth_headers(_chat_api_key()),
        )
        models_ok = models_resp.status_code < 500
        if models_resp.status_code < 300:
            body = models_resp.json()
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, list):
                model_ids = [
                    str(row.get("id"))
                    for row in data
                    if isinstance(row, dict) and row.get("id")
                ]
        out["models"] = {"ok": models_ok, "status": models_resp.status_code, "ids": model_ids[:20]}
    except Exception as exc:
        out["models"] = {"ok": False, "error": str(exc)[:120]}

    embed_ok = False
    try:
        embed_resp = await client.post(
            f"{_api_v1_base()}/embeddings",
            headers=_auth_headers(_embed_api_key()),
            json={"model": settings.forge_embed_model, "input": "ping"},
        )
        embed_ok = embed_resp.status_code < 500
        out["embed"] = {"ok": embed_ok, "status": embed_resp.status_code}
    except Exception as exc:
        out["embed"] = {"ok": False, "error": str(exc)[:120]}

    rerank_ok = False
    if forge_rerank_active():
        try:
            rerank_resp = await client.post(
                f"{_api_v1_base()}/rerank",
                headers=_auth_headers(_rerank_api_key()),
                json={
                    "model": settings.forge_rerank_model,
                    "query": "ping",
                    "documents": ["alpha", "beta"],
                    "top_n": 2,
                },
            )
            rerank_ok = rerank_resp.status_code < 500
            out["rerank"] = {"ok": rerank_ok, "status": rerank_resp.status_code}
        except Exception as exc:
            out["rerank"] = {"ok": False, "error": str(exc)[:120]}

    out["ok"] = bool(
        (out.get("health") or {}).get("ok")
        and (out.get("models") or {}).get("ok")
        and (out.get("embed") or {}).get("ok")
        and (not forge_rerank_active() or (out.get("rerank") or {}).get("ok"))
    )
    return out
