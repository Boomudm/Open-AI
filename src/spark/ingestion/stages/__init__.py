"""Ingest pipeline stages."""

from spark.ingestion.stages.common import apply_alias_resolution, document_registry_updates, empty_index_failure
from spark.ingestion.stages.runner import run_staged_pipeline

__all__ = [
    "apply_alias_resolution",
    "document_registry_updates",
    "empty_index_failure",
    "run_staged_pipeline",
]
