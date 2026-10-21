"""Cross-encoder reranker — GPU batching, session cache, production device guard."""

from __future__ import annotations

import asyncio
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Sequence

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import reranker_degraded_total, reranker_queue_depth
from spark.core.production_profile import ProductionProfile
from spark.retrieval.rerank.cache import get_cached_rerank_scores, store_rerank_scores

log = get_logger(__name__)


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class RerankCacheContext:
    session_id: str
    question: str
    chunk_ids: list[str]
    generations: list[int | None] | None = None


def resolve_rerank_device() -> str:
    configured = (settings.rag_rerank_device or "auto").strip().lower()
    if configured in {"cpu", "cuda", "mps"}:
        return configured
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def validate_gpu_rerank_at_startup() -> None:
    """Fail fast in production when GPU rerank is required but unavailable."""
    profile = ProductionProfile.from_settings()
    if not profile.require_gpu_rerank:
        return
    from spark.core.gpu_sidecar import sidecar_enabled

    if sidecar_enabled():
        log.info("rerank_gpu_sidecar_configured")
        return
    from spark.core.forge_client import forge_rerank_active

    if forge_rerank_active():
        log.info("rerank_forge_configured")
        return
    allow_cpu = os.getenv("SPARK_ALLOW_CPU_RERANK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if allow_cpu:
        log.warning("rerank_cpu_override", reason="SPARK_ALLOW_CPU_RERANK")
        return
    device = resolve_rerank_device()
    if device == "cpu":
        raise RuntimeError(
            "Production profile requires GPU rerank (cuda/mps) but none detected. "
            "Set SPARK_ALLOW_CPU_RERANK=1 for dev laptops only."
        )


class CrossEncoderReranker:
    """Singleton cross-encoder with batched GPU inference."""

    _instance: CrossEncoderReranker | None = None
    _lock = threading.Lock()

    _MAX_INIT_RETRIES = 3
    _RETRY_BACKOFF_SEC = 30.0

    def __init__(self) -> None:
        self._encoder: Any | None = None
        self._init_fail_count = 0
        self._init_fail_time: float = 0.0
        self._init_lock = threading.Lock()
        self._predict_lock = threading.Lock()
        self._queue_depth = 0
        self._queue_depth_lock = threading.Lock()
        # Set for the entire executor job (sidecar *or* CPU). asyncio.wait_for()
        # cannot cancel a running thread — when the async layer times out the
        # thread keeps going. Without this flag the busy-skip only watched
        # _queue_depth (CPU path only), so a timed-out sidecar call that was
        # still blocking in httpx looked "idle" and the next request queued
        # behind it, or worse, the degraded path called sync score_pairs and
        # loaded the 2.2GB CPU model for minutes.
        self._in_flight = False
        self._in_flight_lock = threading.Lock()
        # Dedicated single-worker executor for CE inference. asyncio.wait_for()
        # cannot cancel a running thread-pool task — once encoder.predict() has
        # started it runs to completion regardless of the caller's timeout. A
        # dedicated pool keeps that zombie work from starving the default
        # executor (used elsewhere for unrelated sync-to-async calls), and
        # _queue_depth (set only for the lifetime of the actual thread, not
        # the awaiting coroutine) lets score_pairs_async refuse to queue a
        # second call behind a still-running zombie instead of piling up wait
        # time across requests.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ce-rerank")

    @classmethod
    def get(cls) -> CrossEncoderReranker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def is_available(self) -> bool:
        from spark.core.forge_client import forge_rerank_active

        if forge_rerank_active():
            return True
        return self._load_encoder() is not None

    def _load_encoder(self) -> Any | None:
        import time as _time

        if self._encoder is not None:
            return self._encoder
        if self._init_fail_count >= self._MAX_INIT_RETRIES:
            elapsed = _time.monotonic() - self._init_fail_time
            if elapsed < self._RETRY_BACKOFF_SEC * self._init_fail_count:
                return None
        with self._init_lock:
            if self._encoder is not None:
                return self._encoder
            try:
                from sentence_transformers import CrossEncoder

                device = resolve_rerank_device()
                model_name = getattr(settings, "reranker_model", "BAAI/bge-reranker-v2-m3")
                max_length = int(getattr(settings, "reranker_max_length", 1024))
                try:
                    # Prefer the already-cached local snapshot so a load never
                    # blocks on an outbound HF Hub connectivity check — a slow
                    # or flaky network turns a sub-second load into minutes.
                    self._encoder = CrossEncoder(
                        model_name, max_length=max_length, device=device, local_files_only=True
                    )
                except Exception:
                    self._encoder = CrossEncoder(model_name, max_length=max_length, device=device)
                self._init_fail_count = 0
                log.info("reranker_service_ready", model=model_name, device=device)
                return self._encoder
            except Exception as exc:
                self._init_fail_count += 1
                self._init_fail_time = _time.monotonic()
                log.warning(
                    "reranker_service_unavailable",
                    error=str(exc)[:200],
                    retry_count=self._init_fail_count,
                )
                reranker_degraded_total.labels(reason="model_unavailable").inc()
                return None

    def _clear_in_flight(self) -> None:
        with self._in_flight_lock:
            self._in_flight = False

    def _cpu_score_job(self, query: str, doc_texts: Sequence[str]) -> list[float] | None:
        try:
            return self._score_pairs_uncached(query, doc_texts)
        finally:
            self._clear_in_flight()

    def _score_pairs_uncached(self, query: str, doc_texts: Sequence[str]) -> list[float] | None:
        # Prefer the GPU sidecar when configured — ~25x faster than CPU predict
        # on this Jetson (34 pairs: ~0.6s vs 20-80s). It returns RAW logits, so
        # we apply the same _sigmoid the CPU path uses → identical final scores.
        # Async callers use rerank_scores_async directly (see score_pairs_async);
        # this sync entrypoint keeps sidecar for diversify.py fallbacks. Forge is
        # now the secondary reranker, because the on-box sidecar is lower-latency
        # and avoids remote /v1/rerank timeouts on production queries.
        from spark.core.gpu_sidecar import rerank_scores, sidecar_enabled

        if sidecar_enabled():
            raw_remote = rerank_scores(query, list(doc_texts))
            if raw_remote is not None:
                scores = [_sigmoid(float(v)) for v in raw_remote]
                if scores:
                    top3 = sorted(scores, reverse=True)[:3]
                    log.info(
                        "rag_rerank_ce_scores",
                        top3=[round(s, 4) for s in top3],
                        pairs=len(scores),
                        backend="gpu_sidecar",
                    )
                return scores

        from spark.core.forge_client import forge_rerank_active, rerank_scores as forge_rerank

        if forge_rerank_active():
            scores = forge_rerank(query, list(doc_texts))
            if scores is not None:
                if scores:
                    top3 = sorted(scores, reverse=True)[:3]
                    log.info(
                        "rag_rerank_ce_scores",
                        top3=[round(s, 4) for s in top3],
                        pairs=len(scores),
                        backend="forge",
                    )
                return scores
            log.warning("rag_rerank_forge_unavailable", fallback="cpu")

        if sidecar_enabled():
            # Sidecar is the production GPU path on this Jetson — falling through
            # to the in-process CPU cross-encoder loads ~2.2GB and can take
            # minutes. Degrade immediately; callers use fusion-rank fallback.
            return None

        encoder = self._load_encoder()
        if encoder is None:
            return None
        batch_size = max(1, int(settings.rag_rerank_batch_size or 64))
        with self._queue_depth_lock:
            self._queue_depth += 1
            reranker_queue_depth.set(self._queue_depth)
        try:
            scores: list[float] = []
            with self._predict_lock:
                for start in range(0, len(doc_texts), batch_size):
                    batch = doc_texts[start : start + batch_size]
                    raw = encoder.predict([[query, text] for text in batch])
                    scores.extend(_sigmoid(float(value)) for value in raw)
            if scores:
                top3 = sorted(scores, reverse=True)[:3]
                log.info(
                    "rag_rerank_ce_scores",
                    top3=[round(s, 4) for s in top3],
                    pairs=len(scores),
                )
            return scores
        finally:
            with self._queue_depth_lock:
                self._queue_depth = max(0, self._queue_depth - 1)
                reranker_queue_depth.set(self._queue_depth)

    def score_pairs(self, query: str, doc_texts: Sequence[str]) -> list[float] | None:
        if not doc_texts:
            return []
        return self._score_pairs_uncached(query, doc_texts)

    async def score_pairs_async(
        self,
        query: str,
        doc_texts: Sequence[str],
        *,
        cache_context: RerankCacheContext | None = None,
    ) -> list[float] | None:
        if not doc_texts:
            return []

        chunk_ids = (
            cache_context.chunk_ids
            if cache_context is not None
            else [str(i) for i in range(len(doc_texts))]
        )
        generations = cache_context.generations if cache_context is not None else None
        cached_scores: dict[str, float] = {}
        if cache_context is not None:
            cached_scores = await get_cached_rerank_scores(
                cache_context.session_id,
                cache_context.question,
                chunk_ids,
                generations=generations,
            )

        pending_indices: list[int] = []
        pending_texts: list[str] = []
        merged: list[float | None] = [None] * len(doc_texts)
        for idx, text in enumerate(doc_texts):
            chunk_id = chunk_ids[idx] if idx < len(chunk_ids) else str(idx)
            if chunk_id in cached_scores:
                merged[idx] = cached_scores[chunk_id]
            else:
                pending_indices.append(idx)
                pending_texts.append(text)

        if pending_texts:
            with self._in_flight_lock:
                if self._in_flight or self._queue_depth > 0:
                    # A previous call already timed out at the async layer but its
                    # thread is still executing sidecar I/O or encoder.predict()
                    # in the background (threads can't be cancelled). Queueing
                    # behind it would just add this request's wait on top of that
                    # unbounded remainder — degrade immediately instead.
                    log.warning(
                        "rag_rerank_busy_skip",
                        reason="previous_ce_call_still_running",
                        in_flight=self._in_flight,
                        queue_depth=self._queue_depth,
                        pending=len(pending_texts),
                    )
                    reranker_degraded_total.labels(reason="ce_busy").inc()
                    return None
                self._in_flight = True
            from spark.core.gpu_sidecar import rerank_scores_async, sidecar_enabled

            partial: list[float] | None = None
            try:
                # Fallback chain: a broken/slow primary reranker (e.g. the remote
                # Forge /v1/rerank hanging) must degrade to the next healthy
                # backend, not to zero-score fusion — otherwise real retrieved
                # evidence is dropped and the answer becomes a false "no data".
                if sidecar_enabled():
                    raw = await rerank_scores_async(query, pending_texts)
                    if raw is not None:
                        partial = [_sigmoid(float(v)) for v in raw]
                        if partial:
                            top3 = sorted(partial, reverse=True)[:3]
                            log.info(
                                "rag_rerank_ce_scores",
                                top3=[round(s, 4) for s in top3],
                                pairs=len(partial),
                                backend="gpu_sidecar",
                            )
                    else:
                        log.warning("rag_rerank_gpu_sidecar_unavailable", fallback="forge_or_cpu")

                from spark.core.forge_client import forge_rerank_active, rerank_scores_async as forge_rerank_async

                if partial is None and forge_rerank_active():
                    partial = await forge_rerank_async(query, pending_texts)
                    if partial:
                        top3 = sorted(partial, reverse=True)[:3]
                        log.info(
                            "rag_rerank_ce_scores",
                            top3=[round(s, 4) for s in top3],
                            pairs=len(partial),
                            backend="forge",
                        )
                    else:
                        log.warning("rag_rerank_forge_unavailable", fallback="cpu")
                if partial is None:
                    loop = asyncio.get_running_loop()
                    partial = await loop.run_in_executor(
                        self._executor,
                        lambda: self._cpu_score_job(query, pending_texts),
                    )
                    if partial:
                        log.info(
                            "rag_rerank_ce_scores",
                            pairs=len(partial),
                            backend="cpu",
                        )
            finally:
                self._clear_in_flight()
            if partial is None:
                return None
            to_store: dict[str, float] = {}
            generations_by_chunk: dict[str, int | None] = {}
            for list_idx, value in enumerate(partial):
                doc_idx = pending_indices[list_idx]
                merged[doc_idx] = value
                if cache_context is not None:
                    chunk_id = chunk_ids[doc_idx] if doc_idx < len(chunk_ids) else str(doc_idx)
                    to_store[chunk_id] = float(value)
                    if generations is not None and doc_idx < len(generations):
                        generations_by_chunk[chunk_id] = generations[doc_idx]
            if cache_context is not None and to_store:
                await store_rerank_scores(
                    cache_context.session_id,
                    cache_context.question,
                    to_store,
                    generations_by_chunk=generations_by_chunk or None,
                )

        if any(score is None for score in merged):
            return None
        return [float(score) for score in merged]


cross_encoder = CrossEncoderReranker.get()

# Back-compat alias
reranker_service = cross_encoder
RerankerService = CrossEncoderReranker
