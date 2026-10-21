from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings

from spark.ingestion.embed_profile import EmbedProfile
from spark.core.cache import Cache, cache_key
from spark.core.config import settings
from spark.core.llm_client import openai_gateway_headers
from spark.core.llm_profile import embedding_dimension, load_llm_profile
from spark.core.logging import get_logger
from spark.core.metrics import embedding_seconds

log = get_logger(__name__)


def assert_dummy_embeddings_allowed() -> None:
    """Fail closed when SPARK_SEED_SKIP_EMBED is set outside test profile."""
    import os

    if os.environ.get("SPARK_SEED_SKIP_EMBED") != "1":
        return
    if settings.spark_profile == "test":
        return
    if settings.allow_dummy_embeddings or settings.spark_testing:
        return
    if os.environ.get("SPARK_TESTING") == "1":
        return
    raise RuntimeError(
        "SPARK_SEED_SKIP_EMBED is forbidden outside SPARK_PROFILE=test "
        "(set SPARK_PROFILE=test for CI or ALLOW_DUMMY_EMBEDDINGS=true for local dev only)"
    )

# Providers that run the dense model locally via sentence-transformers (e.g. BAAI/bge-m3,
# a strong multilingual / cross-lingual encoder — Thai query ↔ English manual).
_LOCAL_ST_PROVIDERS = frozenset({"sentence_transformers", "huggingface", "hf", "bge"})
_FORGE_PROVIDER = "forge"


class ForgeRemoteEmbeddings(Embeddings):
    """Dense embed via ForgeNode /v1/embeddings (bge-m3)."""

    def __init__(self, *, normalize: bool = True) -> None:
        self.normalize = normalize

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from spark.core.forge_client import embed_texts

        vectors = embed_texts(texts, normalize=self.normalize)
        if vectors is None:
            raise RuntimeError("Forge embed failed — check FORGE_BASE_URL and API keys")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


# Attention memory is quadratic in sequence length: a batch of pathological
# 8k-token table-page chunks allocates a ~7.75 GiB buffer, which crashes MPS
# ("Invalid buffer size") and takes minutes per chunk on CPU. Real chunking
# profiles emit ~0.5–1.5k tokens, so a 2048 cap only truncates the dense
# vector of oversized table pages — whose full text is still indexed by the
# sparse leg (tokenizer-based) and Postgres FTS, so tail-row recall survives.
_EMBED_MAX_SEQ_TOKENS = 2048
_EMBED_BATCH_SIZE = 8


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer

    try:
        import torch

        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            # Apple Silicon dev machines: CPU attention over long manual/table
            # chunks (bge-m3 supports 8192 tokens) is minutes per chunk; MPS
            # produces the same vectors (cosine ~1.0) several times faster.
            device = "mps"
        else:
            device = "cpu"
    except Exception:
        device = "cpu"
    model = SentenceTransformer(model_name, device=device)
    if getattr(model, "max_seq_length", 0) and model.max_seq_length > _EMBED_MAX_SEQ_TOKENS:
        model.max_seq_length = _EMBED_MAX_SEQ_TOKENS
    log.info(
        "sentence_transformer_load",
        model=model_name,
        device=device,
        max_seq_length=getattr(model, "max_seq_length", None),
    )
    return model


class SentenceTransformerEmbeddings(Embeddings):
    """LangChain Embeddings backed by a local sentence-transformers model.

    Vectors are L2-normalized so Qdrant cosine distance is exact. bge-m3 is symmetric
    (no query/document instruction prefix), so query and document encoding match.
    """

    def __init__(
        self, model_name: str, *, normalize: bool = True, batch_size: int = _EMBED_BATCH_SIZE
    ) -> None:
        self.model_name = model_name
        self.normalize = normalize
        self.batch_size = batch_size

    def _encode(self, texts: list[str]) -> list[list[float]]:
        from spark.core.forge_client import embed_texts as forge_embed_texts, forge_enabled

        if forge_enabled():
            remote = forge_embed_texts(texts, normalize=self.normalize)
            if remote is not None:
                return remote
            if settings.gpu_sidecar_required:
                raise RuntimeError("Forge embed failed and GPU_SIDECAR_REQUIRED=true")

        # Prefer the GPU sidecar when configured — it produces byte-for-byte
        # equivalent vectors (verified cosine 1.0 vs this CPU path) but ~7x
        # faster. Any sidecar failure returns None and we fall through to the
        # in-process CPU model below, so retrieval never breaks.
        from spark.core.gpu_sidecar import embed_texts, sidecar_enabled

        if sidecar_enabled():
            remote = embed_texts(texts, normalize=self.normalize)
            if remote is not None:
                return remote
            if settings.gpu_sidecar_required:
                raise RuntimeError("GPU sidecar embed failed and GPU_SIDECAR_REQUIRED=true")

        model = _load_sentence_transformer(self.model_name)
        vectors = model.encode(
            texts,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


def _assert_embedding_dims(vectors: list[list[float]], *, where: str) -> None:
    """Fail loudly on dimension drift / empty vectors before they reach Qdrant.

    A silent dim mismatch (model swap, gateway error, truncated response) otherwise
    corrupts the vector store and degrades retrieval invisibly.
    """
    if not vectors:
        return
    expected = embedding_dimension()
    for i, vec in enumerate(vectors):
        actual = len(vec) if vec is not None else 0
        if actual != expected:
            raise RuntimeError(
                f"embedding dimension mismatch ({where}): vector {i} has dim {actual}, "
                f"expected {expected} for LLM_PROFILE={settings.llm_profile!r}. "
                "Re-ingest after an embedding model/profile change."
            )


class Embedder:
    _instance: "Embedder | None" = None
    _model: Embeddings | None = None

    @classmethod
    def get(cls) -> "Embedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _build(self) -> Embeddings:
        """Build the embedding client from the active LLM profile.

        Mirrors ``llm_client.get_chat_llm``: an ``openai``/``vllm`` profile routes
        embeddings through an OpenAI-compatible endpoint (e.g. the api.kcalsion.com
        gateway); anything else falls back to native Ollama. The API key falls back
        to ``settings.ollama_api_key`` so secrets stay in .env, not the tracked YAML.
        """
        try:
            profile = load_llm_profile()
        except (KeyError, ValueError):
            profile = {}

        provider = str(
            profile.get("embed_provider") or profile.get("provider") or "ollama"
        ).lower()
        model = profile.get("embed_model") or settings.ollama_embed_model

        if provider == _FORGE_PROVIDER:
            from spark.core.forge_client import forge_enabled

            if not forge_enabled():
                raise RuntimeError("embed_provider=forge requires FORGE_BASE_URL")
            return ForgeRemoteEmbeddings(normalize=True)

        if provider in _LOCAL_ST_PROVIDERS:
            return SentenceTransformerEmbeddings(model, normalize=True)

        if provider in ("openai", "vllm"):
            base_url = (
                profile.get("embed_base_url")
                or profile.get("base_url")
                or settings.ollama_base_url
            ).rstrip("/")
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            embed_api_key = (
                profile.get("embed_api_key")
                or settings.ollama_embed_api_key
                or profile.get("api_key")
                or settings.ollama_api_key
                or "spark-local"
            )
            return OpenAIEmbeddings(
                model=model,
                base_url=base_url,
                api_key=embed_api_key,
                default_headers=openai_gateway_headers(),
                # Ollama-backed gateways reject pre-tokenised int arrays — send raw strings.
                check_embedding_ctx_length=False,
            )

        base_url = profile.get("embed_base_url") or settings.ollama_base_url
        return OllamaEmbeddings(base_url=base_url, model=model)

    def _embeddings(self) -> Embeddings:
        if self._model is None:
            self._model = self._build()
        return self._model

    def embed_profile(self) -> EmbedProfile:
        return EmbedProfile.from_runtime()

    def _query_cache_key(self, text: str) -> str:
        try:
            profile: dict[str, Any] = load_llm_profile()
        except (KeyError, ValueError):
            profile = {}
        provider = str(
            profile.get("embed_provider") or profile.get("provider") or "ollama"
        ).lower()
        model = profile.get("embed_model") or settings.ollama_embed_model
        dim = profile.get("embed_dim") or settings.ollama_embed_dim
        normalized = " ".join((text or "").split())
        return cache_key("embed_query", settings.llm_profile, provider, model, dim, normalized)

    async def embed_query(self, text: str) -> list[float]:
        ttl = int(getattr(settings, "rag_query_embedding_cache_ttl", 0) or 0)
        ck = self._query_cache_key(text) if ttl > 0 else ""
        if ck:
            cached = await Cache.get().get_json(ck)
            if isinstance(cached, list) and cached:
                return [float(v) for v in cached]

        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        try:
            vector = await loop.run_in_executor(None, self._embeddings().embed_query, text)
        finally:
            embedding_seconds.observe(time.perf_counter() - start)
        _assert_embedding_dims([vector], where="embed_query")
        if ck:
            await Cache.get().set_json(ck, vector, ttl=ttl)
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import os

        if os.environ.get("SPARK_SEED_SKIP_EMBED") == "1":
            assert_dummy_embeddings_allowed()
            from spark.core.llm_profile import embedding_dimension

            log.warning(
                "embedder_skip_ollama",
                msg="SPARK_SEED_SKIP_EMBED=1 — dummy vectors; RAG retrieval quality degraded",
            )
            dim = embedding_dimension()
            out: list[list[float]] = []
            for text in texts:
                digest = hashlib.sha256(text.encode()).digest()
                vec = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(dim)]
                out.append(vec)
            return out
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        try:
            vectors = await loop.run_in_executor(None, self._embeddings().embed_documents, texts)
        finally:
            embedding_seconds.observe(time.perf_counter() - start)
        _assert_embedding_dims(vectors, where="embed_documents")
        return vectors
