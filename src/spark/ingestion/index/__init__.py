from spark.ingestion.index.postgres_writer import ALLOWED_POSTGRES_TABLES, PostgresRouter
from spark.ingestion.index.qdrant_writer import QdrantRouter, QdrantWriter
from spark.ingestion.index.embedder import Embedder
from spark.ingestion.index.sparse.encoder import SparseEncoder, SparseEncoderFactory, get_sparse_encoder

PostgresWriter = PostgresRouter

__all__ = [
    "ALLOWED_POSTGRES_TABLES",
    "Embedder",
    "PostgresRouter",
    "PostgresWriter",
    "QdrantRouter",
    "QdrantWriter",
    "SparseEncoder",
    "SparseEncoderFactory",
    "get_sparse_encoder",
]
