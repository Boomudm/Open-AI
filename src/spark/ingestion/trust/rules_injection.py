"""Indirect prompt-injection pattern detection."""

from __future__ import annotations

import re

from .models import PolicyFinding
from .normalize import normalize_policy_text


def validate_injection_patterns(patterns: list[str]) -> None:
    """Fail fast on invalid regex — never silently skip at runtime."""
    for idx, pattern in enumerate(patterns):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid injection pattern at index {idx}: {exc}") from exc


def scan_injection_patterns(
    text: str,
    patterns: list[str],
) -> list[PolicyFinding]:
    normalized = normalize_policy_text(text)
    findings: list[PolicyFinding] = []
    for idx, pattern in enumerate(patterns):
        match = re.search(pattern, normalized)
        if not match:
            continue
        findings.append(
            PolicyFinding(
                rule_id=f"injection:{idx}",
                severity="high",
                message="Potential indirect prompt injection in document text",
                matched_text=match.group(0)[:200],
                category="injection",
            )
        )
    return findings
