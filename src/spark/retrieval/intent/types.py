"""Shared intent routing types (Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QueryIntent(str, Enum):
    PART_LOOKUP = "part_lookup"
    ALARM_DIAGNOSTIC = "alarm_diagnostic"
    PROCEDURE = "procedure"
    SAFETY_LOTO = "safety_loto"
    IO_MAPPING = "io_mapping"
    DRAWING = "drawing"
    GENERAL = "general"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentPlan:
    intent: QueryIntent
    dense_weight: float
    lexical_weight: float
    document_type_hint: str | None
    min_rerank_score: float | None = None
    strict_document_type_filter: bool = False
    weight_version: int = 2
    classifier_confidence: float | None = None
    route_source: str = "rules"
    clarification_suggested: bool = False
