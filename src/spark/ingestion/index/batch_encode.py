"""Synchronous batch encode helpers — run inside the dedicated ingest compute pool."""

from __future__ import annotations

import hashlib
import os
import time

from qdrant_client.models import SparseVector

from spark.core.metrics import embedding_seconds, sparse_encode_empty_total
from spark.ingestion.index.embedder import Embedder, _assert_embedding_dims, assert_dummy_embeddings_allowed
from spark.ingestion.index.sparse.encoder import get_sparse_encoder


def encode_dense_sync(texts: list[str]) -> list[list[float]]:
    """Dense embed batch on a worker thread (not the asyncio event loop)."""
    if not texts:
        return []

    if os.environ.get("SPARK_SEED_SKIP_EMBED") == "1":
        assert_dummy_embeddings_allowed()
        from spark.core.llm_profile import embedding_dimension

        dim = embedding_dimension()
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(dim)]
            out.append(vec)
        return out

    embedder = Embedder.get()
    start = time.perf_counter()
    try:
        vectors = embedder._embeddings().embed_documents(texts)
    finally:
        embedding_seconds.observe(time.perf_counter() - start)
    _assert_embedding_dims(vectors, where="encode_dense_sync")
    return vectors


def encode_sparse_sync_batch(texts: list[str]) -> list[SparseVector]:
    """Sparse encode batch on a worker thread."""
    if not texts:
        return []

    encoder = get_sparse_encoder()
    encode_documents = getattr(encoder, "encode_documents", None)
    if callable(encode_documents):
        vectors = encode_documents(texts)
    else:
        vectors = [encoder.encode_document(text) for text in texts]

    for vec in vectors:
        if not vec.indices:
            sparse_encode_empty_total.inc()
    return vectors
