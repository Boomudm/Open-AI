"""Trust boundary scan result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

Severity = Literal["low", "medium", "high", "critical"]
PolicyAction = Literal["allow", "quarantine", "block"]


class PolicyDecision(str, Enum):
    APPROVE = "approve"
    QUARANTINE = "quarantine"
    BLOCK = "block"


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY_ORDER = {
    FindingSeverity.LOW: 0,
    FindingSeverity.MEDIUM: 1,
    FindingSeverity.HIGH: 2,
    FindingSeverity.CRITICAL: 3,
}


@dataclass(frozen=True)
class PolicyFinding:
    rule_id: str
    severity: Severity
    message: str
    matched_text: str | None = None
    detail: str | None = None
    category: str | None = None

    def resolved_category(self) -> str:
        if self.category:
            return self.category
        return self.rule_id.split(":", 1)[0]

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.matched_text is not None:
            out["matched_text"] = self.matched_text
        if self.detail is not None:
            out["detail"] = self.detail
        return out


@dataclass
class PolicyResult:
    action: PolicyAction
    findings: list[PolicyFinding] = field(default_factory=list)
    policy_version: str = "0"
    risk_score: float = 0.0
    decision: PolicyDecision = PolicyDecision.APPROVE

    def findings_summary(self) -> list[dict[str, Any]]:
        return [f.as_dict() for f in self.findings]

    @property
    def max_severity(self) -> FindingSeverity | None:
        if not self.findings:
            return None
        best = FindingSeverity.LOW
        for finding in self.findings:
            sev = FindingSeverity(finding.severity)
            if _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[best]:
                best = sev
        return best


def severity_at_least(actual: FindingSeverity, threshold: str) -> bool:
    try:
        floor = FindingSeverity(threshold.lower())
    except ValueError:
        floor = FindingSeverity.HIGH
    return _SEVERITY_ORDER[actual] >= _SEVERITY_ORDER[floor]
