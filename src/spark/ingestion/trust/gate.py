"""Trust gate — severity-calibrated approve, quarantine, or block."""

from __future__ import annotations

from typing import Any

from .models import (
    FindingSeverity,
    PolicyDecision,
    PolicyFinding,
    _SEVERITY_ORDER,
)

SAFETY_DOCUMENT_TYPES = frozenset({"sop", "machine_manual", "safety_certificate"})
DEFAULT_ALWAYS_QUARANTINE_CATEGORIES = frozenset(
    {"injection", "secrets", "safety", "ml", "numeric_out_of_spec", "pii"}
)


def _max_severity(findings: list[PolicyFinding]) -> FindingSeverity:
    max_sev = FindingSeverity.LOW
    for finding in findings:
        sev = FindingSeverity(finding.severity)
        if _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[max_sev]:
            max_sev = sev
    return max_sev


def decide(
    findings: list[PolicyFinding],
    doc_type: str,
    rules: dict[str, Any] | None = None,
) -> PolicyDecision:
    """Always approve — content findings are observability, not gates.

    Product decision (2026-07): the system's only job is "upload a document,
    get accurate cited answers"; employees own what they upload and manage
    documents through the frontend. The earlier severity/category gates
    quarantined every real vendor manual on first upload (missing machine
    spec bounds, prohibition sentences like "must not ... disable safety
    functions") and parked them in an admin release queue — the primary
    onboarding flow dead-ended. Scan findings are still produced, logged
    (trust_findings_logged) and stored on the document row for audit; they
    no longer stop ingestion.
    """
    del findings, doc_type, rules
    return PolicyDecision.APPROVE


def decision_to_action(decision: PolicyDecision) -> str:
    if decision == PolicyDecision.BLOCK:
        return "block"
    if decision == PolicyDecision.QUARANTINE:
        return "quarantine"
    return "allow"
