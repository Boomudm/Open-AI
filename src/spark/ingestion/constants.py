"""Ingest pipeline constants — native-only production spine."""

from __future__ import annotations

from typing import Literal

IngestBackend = Literal["native"]

INGEST_BACKEND: IngestBackend = "native"

DEDUP_STRATEGIES: frozenset[str] = frozenset({"skip_if_exists", "reingest_replace"})
