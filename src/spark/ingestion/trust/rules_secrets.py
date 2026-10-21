"""Secret and PII pattern detection for ingest quarantine."""

from __future__ import annotations

import re

from spark.ingestion.trust.models import PolicyFinding
from spark.ingestion.trust.normalize import normalize_policy_text

_SECRET_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (r"(?i)\bAKIA[0-9A-Z]{16}\b", "aws_access_key", "critical"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "private_key", "critical"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.", "jwt_token", "high"),
    (r"(?i)\b(api[_-]?key|secret[_-]?key|password)\s*[:=]\s*\S{8,}", "credential_assignment", "high"),
    (r"\b[0-9]{1}-[0-9]{4}-[0-9]{5}-[0-9]{2}-[0-9]\b", "thai_national_id", "high"),
)


def scan_secrets(text: str) -> list[PolicyFinding]:
    if not text.strip():
        return []
    normalized = normalize_policy_text(text)
    findings: list[PolicyFinding] = []
    for pattern, rule_id, severity in _SECRET_PATTERNS:
        match = re.search(pattern, normalized)
        if not match:
            continue
        findings.append(
            PolicyFinding(
                rule_id=f"secrets:{rule_id}",
                severity=severity,  # type: ignore[arg-type]
                message=f"Potential secret or PII detected ({rule_id})",
                matched_text=match.group(0)[:120],
                category="secrets",
            )
        )
    return findings
