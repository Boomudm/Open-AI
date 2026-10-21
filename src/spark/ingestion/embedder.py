"""Compatibility shim — use spark.ingestion.index.embedder."""
from spark.ingestion.index import embedder as _embedder_module
from spark.ingestion.index.embedder import *  # noqa: F403

_load_sentence_transformer = _embedder_module._load_sentence_transformer
