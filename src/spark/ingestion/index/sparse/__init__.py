"""Sparse vector encoders for Qdrant hybrid search (Phase 5)."""

from spark.ingestion.index.sparse.encoder import SparseEncoder, SparseEncoderFactory, get_sparse_encoder

__all__ = ["SparseEncoder", "SparseEncoderFactory", "get_sparse_encoder"]
