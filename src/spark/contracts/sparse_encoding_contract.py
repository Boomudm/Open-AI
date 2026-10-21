"""Sparse encoding symmetry — index and retrieval share one encoder factory."""

from __future__ import annotations

from spark.ingestion.index.sparse.encoder import SparseEncoder, get_sparse_encoder


def index_sparse_encoder() -> SparseEncoder:
    """Encoder used when writing Qdrant points during ingest."""
    return get_sparse_encoder()


def retrieval_sparse_encoder() -> SparseEncoder:
    """Encoder used when building hybrid query vectors — must match index path."""
    return get_sparse_encoder()
