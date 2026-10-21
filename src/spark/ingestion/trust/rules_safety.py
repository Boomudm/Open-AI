"""Safety-critical phrase detection (LOTO bypass, interlock override)."""

from __future__ import annotations

import re

from .models import PolicyFinding
from .normalize import normalize_policy_text
from .rules_injection import validate_injection_patterns

# Vendor manuals legitimately *prohibit* the flagged behaviour — the real KUKA
# KR C5 manual says "Additional components must not impair or disable safety
# functions" and was quarantined for it. A phrase preceded by a negation or
# prohibition is a warning, not bypass language. Window is chars, applied to
# normalized text immediately before the match.
_NEGATION_BEFORE_RE = re.compile(
    r"(?i)\b(?:must\s+not|do(?:es)?\s+not|don'?t|never|not\s+(?:be\s+)?(?:allowed|permitted)"
    r"(?:\s+to)?|prohibited\s+(?:from|to)|forbidden\s+to|ห้าม|อย่า)\s*(?:\w+\s+){0,2}$"
)
_NEGATION_WINDOW_CHARS = 60


def _is_negated(normalized: str, start: int) -> bool:
    prefix = normalized[max(0, start - _NEGATION_WINDOW_CHARS) : start]
    return bool(_NEGATION_BEFORE_RE.search(prefix))


def scan_safety_phrases(
    text: str,
    patterns: list[str],
) -> list[PolicyFinding]:
    validate_injection_patterns(patterns)
    normalized = normalize_policy_text(text)
    findings: list[PolicyFinding] = []
    for idx, pattern in enumerate(patterns):
        for match in re.finditer(pattern, normalized):
            if _is_negated(normalized, match.start()):
                continue
            findings.append(
                PolicyFinding(
                    rule_id=f"safety:{idx}",
                    severity="medium",
                    message="Safety-critical bypass language detected",
                    matched_text=match.group(0)[:200],
                    category="safety",
                )
            )
            break
    return findings
