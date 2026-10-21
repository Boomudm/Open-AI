"""Production startup checks — fail fast or warn on misconfiguration.

Checks run inside the FastAPI lifespan before serving requests:
  1. LLM proxy reachability (proxy.py:9090 for gemma/gemma_remote profiles)
  2. BGE-M3 embedder warmup (prevents first-query cold-start timeout on A16)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from spark.core.logging import get_logger

log = get_logger(__name__)

_LLM_PROXY_PROFILES = frozenset({"gemma", "gemma_remote", "forge_remote", "kcalsion_gateway"})
_WARMUP_SENTENCE = "ทดสอบ warmup ระบบ embedder"


async def check_forge_reachable() -> None:
    """Probe ForgeNode /health + embed when FORGE_BASE_URL is configured."""
    try:
        from spark.core.forge_client import fetch_forge_status, forge_enabled
    except Exception:
        return
    if not forge_enabled():
        return
    try:
        status = await fetch_forge_status()
        if status.get("ok"):
            log.info(
                "startup_forge_ok",
                base_url=status.get("base_url"),
                embed=(status.get("embed") or {}).get("ok"),
                rerank=(status.get("rerank") or {}).get("ok"),
            )
        else:
            log.warning(
                "startup_forge_degraded",
                base_url=status.get("base_url"),
                health=status.get("health"),
                embed=status.get("embed"),
                rerank=status.get("rerank"),
                models=status.get("models"),
            )
    except Exception as exc:
        log.warning("startup_forge_unreachable", error=str(exc)[:200])


async def check_llm_proxy_reachable() -> None:
    """Ping the LLM proxy base_url/v1/models.

    Logs a WARNING (not an error) if unreachable — query-time circuit breaker
    will handle actual failures. This check exists so ops knows at deploy time
    whether the proxy is up, not at first user request.
    """
    try:
        from spark.core.config import settings
        from spark.core.forge_client import forge_enabled
        from spark.core.llm_profile import load_llm_profile
    except Exception:
        return

    profile_name = settings.llm_profile

    try:
        profile: dict[str, Any] = load_llm_profile(profile_name)
    except (KeyError, ValueError) as exc:
        log.warning("startup_llm_profile_load_failed", profile=profile_name, error=str(exc))
        return

    base_url: str = (profile.get("base_url") or settings.ollama_base_url).rstrip("/")
    if not base_url.endswith("/v1"):
        models_url = f"{base_url}/v1/models"
    else:
        models_url = f"{base_url}/models"

    if profile_name not in _LLM_PROXY_PROFILES and not forge_enabled():
        return

    try:
        import httpx

        from spark.core.llm_client import openai_gateway_headers

        headers = dict(openai_gateway_headers())
        api_key = profile.get("api_key") or settings.ollama_api_key or settings.forge_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(models_url, headers=headers)
        elapsed = round((time.monotonic() - t0) * 1000)
        if resp.status_code < 300:
            log.info(
                "startup_llm_proxy_ok",
                url=models_url,
                status=resp.status_code,
                elapsed_ms=elapsed,
            )
        else:
            log.warning(
                "startup_llm_proxy_unexpected_status",
                url=models_url,
                status=resp.status_code,
                detail="Proxy reachable but returned non-2xx — check proxy.py logs",
            )
    except Exception as exc:
        log.warning(
            "startup_llm_proxy_unreachable",
            url=models_url,
            error=str(exc),
            detail=(
                "LLM proxy is not responding. For gemma profile, ensure proxy.py "
                "is running on the host at port 9090. RAG queries will fail until proxy is up."
            ),
        )


async def warmup_embedder() -> None:
    """Load the sentence-transformer embedder and encode one dummy sentence.

    On A16 (CUDA), model load + first forward pass takes ~5-10s. Running this
    at startup ensures the model is resident in VRAM before the first user query,
    preventing RAG_RERANK_TIMEOUT_SEC budget exhaustion on cold start.
    """
    try:
        from spark.core.config import settings
        from spark.core.llm_profile import load_llm_profile
    except Exception:
        return

    try:
        profile = load_llm_profile(settings.llm_profile)
    except (KeyError, ValueError):
        return

    embed_provider = str(profile.get("embed_provider") or "").lower()
    if embed_provider in {"openai", "vllm", "forge"}:
        return
    if embed_provider != "sentence_transformers":
        return

    embed_model: str = str(profile.get("embed_model", "BAAI/bge-m3"))

    def _load_and_encode() -> int:
        from spark.core.forge_client import embed_texts as forge_embed, forge_enabled
        from spark.core.gpu_sidecar import embed_texts, sidecar_enabled
        from spark.ingestion.index.embedder import _load_sentence_transformer  # type: ignore

        t0 = time.monotonic()
        if forge_enabled():
            vectors = forge_embed([_WARMUP_SENTENCE])
            if vectors is None:
                raise RuntimeError("Forge embed warmup failed")
            return round((time.monotonic() - t0) * 1000)
        if sidecar_enabled():
            vectors = embed_texts([_WARMUP_SENTENCE])
            if vectors is None:
                raise RuntimeError("GPU sidecar embed warmup failed")
            return round((time.monotonic() - t0) * 1000)
        model = _load_sentence_transformer(embed_model)
        model.encode([_WARMUP_SENTENCE], batch_size=1, show_progress_bar=False)
        return round((time.monotonic() - t0) * 1000)

    async def _warmup() -> None:
        try:
            # _load_and_encode is synchronous CPU-bound work (model load +
            # first forward pass) — calling it directly here would block the
            # whole event loop for its entire duration (188s+ observed under
            # load), during which uvicorn can't accept connections or even
            # answer /readyz. run_in_executor keeps startup non-blocking, same
            # pattern the live request path already uses for the reranker.
            loop = asyncio.get_running_loop()
            elapsed = await loop.run_in_executor(None, _load_and_encode)
            log.info(
                "startup_embedder_warmup_ok",
                model=embed_model,
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            log.warning(
                "startup_embedder_warmup_failed",
                model=embed_model,
                error=str(exc),
                detail="Embedder warmup failed — first query may be slower than usual",
            )

    asyncio.create_task(_warmup())


async def warmup_reranker() -> None:
    """Warmup cross-encoder reranker with a dummy pair.

    bge-reranker-v2-m3 on CUDA: first forward pass ~3-5s (model load + JIT).
    Running at startup ensures the 15s RAG_RERANK_TIMEOUT_SEC budget is not
    consumed by cold-start on the first real query.
    """
    try:
        from spark.core.config import settings
    except Exception:
        return

    if not settings.rag_rerank_enabled:
        return

    def _score_dummy() -> int:
        from spark.retrieval.rerank.cross_encoder import cross_encoder  # type: ignore

        t0 = time.monotonic()
        cross_encoder.score_pairs(_WARMUP_SENTENCE, [_WARMUP_SENTENCE])
        return round((time.monotonic() - t0) * 1000)

    async def _warmup() -> None:
        try:
            # Same event-loop-blocking issue as warmup_embedder above — run
            # the synchronous model load + predict() off the event loop.
            loop = asyncio.get_running_loop()
            elapsed = await loop.run_in_executor(None, _score_dummy)
            log.info(
                "startup_reranker_warmup_ok",
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            log.warning(
                "startup_reranker_warmup_failed",
                error=str(exc),
                detail="Reranker warmup failed — first query may hit timeout",
            )

    asyncio.create_task(_warmup())


async def warmup_sparse_encoder() -> None:
    """Warm BGE-M3 sparse tokenizer used by hybrid Qdrant retrieval.

    Dense embedder/reranker warmups do not touch the sparse tokenizer cache.
    Without this, the first real hybrid query after restart can spend tens of
    seconds loading tokenizer assets before Qdrant search even starts.
    """

    def _encode_dummy() -> int:
        from spark.contracts.sparse_encoding_contract import retrieval_sparse_encoder

        t0 = time.monotonic()
        encoder = retrieval_sparse_encoder()
        encoder.encode_query(_WARMUP_SENTENCE)
        return round((time.monotonic() - t0) * 1000)

    async def _warmup() -> None:
        try:
            loop = asyncio.get_running_loop()
            elapsed = await loop.run_in_executor(None, _encode_dummy)
            log.info("startup_sparse_encoder_warmup_ok", elapsed_ms=elapsed)
        except Exception as exc:
            log.warning(
                "startup_sparse_encoder_warmup_failed",
                error=str(exc),
                detail="Sparse encoder warmup failed; first hybrid query may be slower than usual",
            )

    asyncio.create_task(_warmup())


async def run_all_startup_checks() -> None:
    """Run all production startup checks. Called from FastAPI lifespan."""
    await check_forge_reachable()
    await check_llm_proxy_reachable()
    await warmup_embedder()
    await warmup_sparse_encoder()
    await warmup_reranker()
