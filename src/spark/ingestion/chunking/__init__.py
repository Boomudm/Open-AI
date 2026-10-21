"""Legacy chunking utilities — canonical strategies live in ``spark.ingestion.chunk``."""

from spark.ingestion.chunking.recursive import recursive_chunk_text

__all__ = ["recursive_chunk_text"]
