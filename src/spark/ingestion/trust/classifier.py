"""Lightweight injection-risk classifier (exemplar similarity, no external API)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .normalize import normalize_policy_text

_EXEMPLARS_PATH = Path(__file__).resolve().parents[4] / "configs" / "trust" / "injection_exemplars.json"

_SAFETY_TYPES = frozenset({"sop", "machine_manual", "safety_certificate"})


@lru_cache(maxsize=1)
def _load_exemplars() -> list[str]:
    if not _EXEMPLARS_PATH.is_file():
        return []
    with _EXEMPLARS_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        raw = data.get("exemplars") or []
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    return [normalize_policy_text(str(item)) for item in raw if str(item).strip()]


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", normalize_policy_text(text).lower()) if len(t) > 2}


def exemplar_max_similarity(text: str) -> float:
    """Jaccard similarity against curated injection exemplars (0..1)."""
    if not text:
        return 0.0
    source = _token_set(text)
    if not source:
        return 0.0
    best = 0.0
    for exemplar in _load_exemplars():
        target = _token_set(exemplar)
        if not target:
            continue
        union = source | target
        if not union:
            continue
        score = len(source & target) / len(union)
        best = max(best, score)
    return best


def classify_risk_score(
    text: str,
    *,
    regex_finding_count: int = 0,
    ocr_confidence_min: float | None = None,
    document_type: str = "",
) -> float:
    """Linear probe on regex hits, exemplar similarity, OCR quality, doc type."""
    exemplar_sim = exemplar_max_similarity(text)
    regex_component = min(1.0, regex_finding_count * 0.35)
    ocr_penalty = 0.0
    if ocr_confidence_min is not None and float(ocr_confidence_min) < 50.0:
        ocr_penalty = 0.15
    safety_boost = 0.1 if document_type in _SAFETY_TYPES else 0.0
    return min(
        1.0,
        0.45 * exemplar_sim + regex_component + ocr_penalty + safety_boost,
    )


async def classify_risk(
    text: str,
    *,
    regex_finding_count: int = 0,
    ocr_confidence_min: float | None = None,
    document_type: str = "",
) -> float | None:
    """Return risk score in [0, 1]; None when text is empty."""
    if not (text or "").strip():
        return None
    return classify_risk_score(
        text,
        regex_finding_count=regex_finding_count,
        ocr_confidence_min=ocr_confidence_min,
        document_type=document_type,
    )


def ml_classifier_enabled() -> bool:
    """Enable ML classifier by default in production."""
    from spark.core.config import settings

    return settings.is_production or settings.spark_profile == "production"
