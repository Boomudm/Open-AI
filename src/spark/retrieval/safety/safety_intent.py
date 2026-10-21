"""Production safety intent detection — rules + optional exemplar overlap (Phase 9)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from spark.retrieval.intent import features

_EXEMPLARS_PATH = Path(__file__).resolve().parents[4] / "configs" / "trust" / "safety_exemplars.json"

_LOTO_PATTERNS = (
    r"\bloto\b",
    r"\blockout\b",
    r"\btagout\b",
    r"\block.?out\b",
    r"\btag.?out\b",
    r"zero[\s-]?energy",
    r"ล็อ?ค.?เอาท์",
    r"ล็อ?ก.?เอาท์",
    r"ติด\s*tag",
    r"ตัด\s*breaker",
)
_OVERRIDE_PATTERNS = (
    r"skip\s+(?:loto|lockout|tagout|lock.?out|tag.?out)",
    r"bypass\s+(?:loto|lockout|tagout|interlock|safety|guard)",
    r"disable\s+safety",
    r"override\s+emergency",
    r"run\s+without\s+guard",
    r"without\s+(?:loto|lockout|tagout)",
    r"ข้าม\s+(?:loto|lockout|tagout)",
    r"ไม่ต้อง\s+(?:loto|lockout|tagout)",
    r"ชั่วคราว.*(?:loto|lockout)",
)
_INTERLOCK_PATTERNS = (
    r"\binterlock\b",
    r"guard\s+bypass",
    r"safety\s+guard",
    r"light\s+curtain",
    r"override\s+interlock",
)


class SafetyIntentKind(str, Enum):
    NONE = "none"
    LOTO = "loto"
    EMERGENCY_OVERRIDE = "emergency_override"
    INTERLOCK = "interlock"


@dataclass(frozen=True)
class SafetyIntent:
    kind: SafetyIntentKind
    confidence: float
    matched_rules: tuple[str, ...] = ()


def _match_any(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


@lru_cache(maxsize=1)
def _load_exemplars() -> dict[str, tuple[str, ...]]:
    if not _EXEMPLARS_PATH.is_file():
        return {}
    raw = json.loads(_EXEMPLARS_PATH.read_text(encoding="utf-8"))
    return {
        key: tuple(str(item) for item in values if isinstance(item, str))
        for key, values in raw.items()
        if isinstance(values, list)
    }


def _exemplar_overlap_score(question: str, kind: SafetyIntentKind) -> float:
    """Lexical overlap against safety exemplar phrases (no embedding model in CI)."""
    exemplars = _load_exemplars().get(kind.value, ())
    if not exemplars:
        return 0.0
    q_tokens = set(re.findall(r"[\w\u0E00-\u0E7F]+", (question or "").lower()))
    if not q_tokens:
        return 0.0
    best = 0.0
    for phrase in exemplars:
        p_tokens = set(re.findall(r"[\w\u0E00-\u0E7F]+", phrase.lower()))
        if not p_tokens:
            continue
        overlap = len(q_tokens & p_tokens) / len(p_tokens)
        best = max(best, overlap)
    return best


def detect_safety_intent(question: str) -> SafetyIntent:
    """Detect safety-critical query intent for production gating (not eval exact match)."""
    q = (question or "").strip()
    if not q:
        return SafetyIntent(kind=SafetyIntentKind.NONE, confidence=0.0)

    matched: list[str] = []

    if _match_any(q, _OVERRIDE_PATTERNS):
        matched.append("override_pattern")
        return SafetyIntent(
            kind=SafetyIntentKind.EMERGENCY_OVERRIDE,
            confidence=0.95,
            matched_rules=tuple(matched),
        )

    if features.has_loto_terms(q) or _match_any(q, _LOTO_PATTERNS):
        matched.append("loto_pattern")
        conf = max(0.85, _exemplar_overlap_score(q, SafetyIntentKind.LOTO))
        return SafetyIntent(
            kind=SafetyIntentKind.LOTO,
            confidence=conf,
            matched_rules=tuple(matched),
        )

    interlock = _match_any(q, _INTERLOCK_PATTERNS)
    if interlock:
        matched.append("interlock_pattern")
        conf = max(0.80, _exemplar_overlap_score(q, SafetyIntentKind.INTERLOCK))
        return SafetyIntent(
            kind=SafetyIntentKind.INTERLOCK,
            confidence=conf,
            matched_rules=tuple(matched),
        )

    for kind in (SafetyIntentKind.LOTO, SafetyIntentKind.EMERGENCY_OVERRIDE, SafetyIntentKind.INTERLOCK):
        overlap = _exemplar_overlap_score(q, kind)
        if overlap >= 0.45:
            matched.append(f"exemplar:{kind.value}")
            return SafetyIntent(kind=kind, confidence=overlap, matched_rules=tuple(matched))

    return SafetyIntent(kind=SafetyIntentKind.NONE, confidence=0.0)


def requires_strict_retrieval(intent: SafetyIntent) -> bool:
    """True when fallback broadening or weak retrieval must fail closed."""
    return intent.kind != SafetyIntentKind.NONE
