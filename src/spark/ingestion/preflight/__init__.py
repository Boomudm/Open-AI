"""Ingest preflight package (Phase 14)."""

from spark.ingestion.preflight.validator import PolicyHint, PreflightResult, run_ingest_preflight

__all__ = ["PolicyHint", "PreflightResult", "run_ingest_preflight"]
