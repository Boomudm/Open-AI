"""Post-chunk policy pass — full-doc sliding window + boundary detection."""

from __future__ import annotations

from spark.ingestion.context import IngestContext
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.trust.classifier import ml_classifier_enabled
from spark.ingestion.trust.document_scan import concat_records, record_text, sliding_windows
from spark.ingestion.trust.gate import decide, decision_to_action
from spark.ingestion.trust.models import PolicyFinding, PolicyResult
from spark.ingestion.trust.rules_injection import scan_injection_patterns
from spark.ingestion.trust.scanner import TrustScanner, _apply_ml_classifier

_BOUNDARY_WINDOW = 160


def _boundary_windows(records: list[ParsedRecord]) -> list[str]:
    windows: list[str] = []
    for index in range(len(records) - 1):
        left = record_text(records[index])[-_BOUNDARY_WINDOW:]
        right = record_text(records[index + 1])[:_BOUNDARY_WINDOW]
        if left or right:
            windows.append(f"{left}{right}")
    return windows


def _dedupe_findings(findings: list[PolicyFinding]) -> list[PolicyFinding]:
    seen: set[tuple[str, str | None]] = set()
    unique: list[PolicyFinding] = []
    for finding in findings:
        key = (finding.rule_id, finding.matched_text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


async def scan_post_chunk_batch(
    records: list[ParsedRecord],
    ctx: IngestContext,
    scanner: TrustScanner,
) -> PolicyResult | None:
    """Re-scan transformed records before embed; catches injection split across chunk edges."""
    if not records:
        return None

    rules = scanner._rules()
    if not rules.get("post_chunk_scan", True):
        return None

    patterns = list(rules.get("injection_patterns") or [])
    findings: list[PolicyFinding] = []

    batch_text = concat_records(records)
    overlap = max(max((len(pattern) for pattern in patterns), default=80), 64)
    window = max(overlap * 2, _BOUNDARY_WINDOW)
    for window_text in sliding_windows(batch_text, window=window, overlap=overlap):
        findings.extend(scan_injection_patterns(window_text, patterns))

    for window in _boundary_windows(records):
        findings.extend(scan_injection_patterns(window, patterns))

    deduped = _dedupe_findings(findings)
    if not deduped and not ml_classifier_enabled():
        return None

    risk_score = max(
        ({"low": 0.2, "medium": 0.55, "high": 0.9, "critical": 1.0}.get(f.severity, 0.0) for f in deduped),
        default=0.0,
    )
    result = PolicyResult(
        action="allow",
        findings=deduped,
        policy_version=scanner.version,
        risk_score=risk_score,
    )

    if ml_classifier_enabled():
        result = await _apply_ml_classifier(
            result,
            text=batch_text,
            document_context={
                **ctx.document_context,
                "document_type": ctx.document_type,
            },
            rules=rules,
        )
        if not result.findings:
            return None
    elif not deduped:
        return None

    decision = decide(result.findings, ctx.document_type, rules)
    action = decision_to_action(decision)
    result.decision = decision
    result.action = action  # type: ignore[assignment]
    return result
