"""Phase 3 — low OCR warnings alone must not quarantine safety documents."""

from __future__ import annotations

from spark.ingestion.trust.gate import decide
from spark.ingestion.trust.models import PolicyFinding
from spark.ingestion.trust.scanner import TrustScanner

_POLICY = {
    "version": "3",
    "rules": {
        "injection_patterns": [],
        "safety_critical_phrases": [],
        "quarantine_document_types": ["sop", "machine_manual", "safety_certificate"],
        "block_on_severity": "high",
        "quarantine_on_severity": "medium",
        "always_quarantine_categories": ["injection", "secrets", "safety", "ml"],
    },
}


def test_low_ocr_finding_does_not_quarantine_sop() -> None:
    findings = [
        PolicyFinding(
            rule_id="ocr_low_confidence",
            severity="low",
            message="OCR confidence below 50%",
            category="ocr",
        )
    ]
    decision = decide(findings, "sop", _POLICY["rules"])
    assert decision.value == "approve"


def test_scan_document_approves_safety_doc_with_only_low_ocr() -> None:
    scanner = TrustScanner(policy=_POLICY)
    result = scanner.scan_document(
        text="Standard operating procedure for bearing lubrication.",
        document_context={"document_type": "sop", "ocr_confidence_min": 42.0},
    )
    assert result.action == "allow"
    assert any(f.rule_id == "ocr_low_confidence" for f in result.findings)
