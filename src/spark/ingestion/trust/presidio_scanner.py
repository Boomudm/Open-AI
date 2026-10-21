"""Presidio-backed PII scan with regex fallback and factory allowlists (Phase 14)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.core.logging import get_logger
from spark.ingestion.trust.models import PolicyFinding

log = get_logger(__name__)

_ALLOWLIST_PATH = Path(__file__).resolve().parents[4] / "configs" / "compliance" / "pii_allowlist.yaml"

_FALLBACK_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (r"\b\d{3}-\d{2}-\d{4}\b", "pii:us_ssn", "critical", "US_SSN"),
    (
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",
        "pii:credit_card",
        "critical",
        "CREDIT_CARD",
    ),
    (
        r"(?i)(?:contact|call|phone).{0,40}\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "pii:phone_contact",
        "high",
        "PHONE_NUMBER",
    ),
)


@dataclass(frozen=True)
class DetectedEntity:
    entity_type: str
    start: int
    end: int
    score: float
    text: str


def presidio_available() -> bool:
    try:
        from presidio_analyzer import AnalyzerEngine  # noqa: F401

        return True
    except ImportError:
        return False


@lru_cache(maxsize=1)
def _load_allowlist_config() -> dict[str, Any]:
    if not _ALLOWLIST_PATH.is_file():
        return {"global": {"patterns": []}, "factories": {}}
    raw = yaml.safe_load(_ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _allowlist_patterns(factory_id: str | None) -> list[tuple[re.Pattern[str], frozenset[str]]]:
    config = _load_allowlist_config()
    patterns: list[dict[str, Any]] = list((config.get("global") or {}).get("patterns") or [])
    factories = config.get("factories") or {}
    if factory_id and isinstance(factories, dict):
        factory_entry = factories.get(factory_id) or {}
        if isinstance(factory_entry, dict):
            patterns.extend(list(factory_entry.get("patterns") or []))
    compiled: list[tuple[re.Pattern[str], frozenset[str]]] = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        regex = str(item.get("regex") or "")
        if not regex:
            continue
        entity_types = frozenset(str(t) for t in (item.get("entity_types") or []))
        compiled.append((re.compile(regex), entity_types))
    return compiled


def _is_allowlisted(entity: DetectedEntity, *, factory_id: str | None) -> bool:
    for pattern, entity_types in _allowlist_patterns(factory_id):
        if entity_types and entity.entity_type not in entity_types:
            continue
        if pattern.search(entity.text):
            return True
    return False


def _fallback_entities(text: str) -> list[DetectedEntity]:
    entities: list[DetectedEntity] = []
    for pattern, _rule_id, _severity, entity_type in _FALLBACK_PATTERNS:
        for match in re.finditer(pattern, text):
            entities.append(
                DetectedEntity(
                    entity_type=entity_type,
                    start=match.start(),
                    end=match.end(),
                    score=0.95,
                    text=match.group(0),
                )
            )
    return entities


@lru_cache(maxsize=1)
def _presidio_engine() -> Any | None:
    if not presidio_available():
        return None
    from presidio_analyzer import AnalyzerEngine

    return AnalyzerEngine()


def _presidio_entities(text: str) -> list[DetectedEntity]:
    engine = _presidio_engine()
    if engine is None:
        return _fallback_entities(text)
    results = engine.analyze(text=text, language="en")
    entities: list[DetectedEntity] = []
    for result in results:
        snippet = text[result.start : result.end]
        entities.append(
            DetectedEntity(
                entity_type=str(result.entity_type),
                start=int(result.start),
                end=int(result.end),
                score=float(result.score),
                text=snippet,
            )
        )
    return entities


def _entity_to_finding(entity: DetectedEntity) -> PolicyFinding:
    if entity.entity_type in {"US_SSN", "US_ITIN"}:
        severity = "critical"
        message = "High-confidence government identifier detected"
    elif entity.entity_type in {"CREDIT_CARD", "IBAN_CODE"}:
        severity = "critical"
        message = "High-confidence payment identifier detected"
    elif entity.entity_type in {"PHONE_NUMBER", "PERSON", "EMAIL_ADDRESS"}:
        severity = "high"
        message = f"PII entity detected ({entity.entity_type})"
    else:
        severity = "medium"
        message = f"Potential PII detected ({entity.entity_type})"
    return PolicyFinding(
        rule_id=f"pii:{entity.entity_type.lower()}",
        severity=severity,  # type: ignore[arg-type]
        message=message,
        matched_text=entity.text[:120],
        category="pii",
    )


def scan_pii(
    text: str,
    *,
    factory_id: str | None = None,
    min_score: float = 0.75,
) -> list[PolicyFinding]:
    if not text.strip():
        return []
    entities = _presidio_entities(text)
    findings: list[PolicyFinding] = []
    seen: set[tuple[str, str]] = set()

    high_confidence_people = [
        entity
        for entity in entities
        if entity.entity_type == "PERSON" and entity.score >= min_score
    ]
    phone_entities = [
        entity
        for entity in entities
        if entity.entity_type == "PHONE_NUMBER" and entity.score >= min_score
    ]

    for entity in entities:
        if entity.score < min_score:
            continue
        if _is_allowlisted(entity, factory_id=factory_id):
            continue
        key = (entity.entity_type, entity.text[:40])
        if key in seen:
            continue
        seen.add(key)
        findings.append(_entity_to_finding(entity))

    if high_confidence_people and phone_entities:
        findings.append(
            PolicyFinding(
                rule_id="pii:name_phone_combo",
                severity="high",
                message="Name and phone number detected in same document",
                category="pii",
            )
        )

    if findings and not presidio_available():
        log.debug("presidio_pii_fallback", finding_count=len(findings))
    return findings
