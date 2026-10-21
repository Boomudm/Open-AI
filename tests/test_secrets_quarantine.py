"""Secrets detection before embed — findings are log-only (no quarantine)."""

from __future__ import annotations

from spark.ingestion.trust.rules_secrets import scan_secrets
from spark.ingestion.trust.scanner import TrustScanner


def test_aws_key_detected_as_critical() -> None:
    findings = scan_secrets("backup key AKIAIOSFODNN7EXAMPLE in repair log")
    assert findings
    assert findings[0].severity == "critical"
    assert findings[0].rule_id.startswith("secrets:")


def test_secrets_scan_logs_but_does_not_gate() -> None:
    """Detection must keep working for audit; the gate is log-only (product
    decision 2026-07 — see trust/gate.py)."""
    scanner = TrustScanner(
        policy={
            "version": "3",
            "rules": {
                "secrets_scan": True,
                "injection_patterns": [],
                "safety_critical_phrases": [],
            },
        }
    )
    result = scanner.scan_document(
        text="Contact admin; api_key=supersecretvalue123",
        document_context={"document_type": "machine_manual"},
    )
    assert result.action == "allow"
    assert any(f.rule_id.startswith("secrets:") for f in result.findings)
