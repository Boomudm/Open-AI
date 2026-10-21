"""Full-document adversarial scan before index swap commit."""

from __future__ import annotations

from typing import Any

from spark.ingestion.document_accumulator import DocumentAccumulator
from spark.ingestion.parsers.base import ParsedRecord

from .classifier import classify_risk, ml_classifier_enabled
from .gate import decide, decision_to_action
from .models import FindingSeverity, PolicyFinding, PolicyResult
from .rules_injection import scan_injection_patterns
from .rules_safety import scan_safety_phrases
from .rules_secrets import scan_secrets

DEFAULT_MAX_SCAN_CHARS = 500_000
_ML_RISK_THRESHOLD = 0.85


def record_text(record: ParsedRecord) -> str:
    return record.text_for_embedding or str(record.payload.get("page_content") or "")


def concat_records(records: list[ParsedRecord], *, max_chars: int = DEFAULT_MAX_SCAN_CHARS) -> str:
    parts: list[str] = []
    total = 0
    for record in records:
        text = record_text(record)
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            parts.append(text[:remaining])
            break
        parts.append(text)
        total += len(text)
    return "".join(parts)


def sliding_windows(text: str, *, window: int, overlap: int) -> list[str]:
    if not text:
        return []
    if len(text) <= window:
        return [text]
    step = max(1, window - overlap)
    windows: list[str] = []
    for start in range(0, len(text), step):
        chunk = text[start : start + window]
        if not chunk:
            break
        windows.append(chunk)
        if start + window >= len(text):
            break
    return windows


def _max_pattern_length(patterns: list[str]) -> int:
    return max((len(pattern) for pattern in patterns), default=80)


async def scan_full(
    records: list[ParsedRecord],
    document_context: dict[str, Any],
    scanner: Any,
    *,
    max_chars: int = DEFAULT_MAX_SCAN_CHARS,
) -> PolicyResult:
    """Regex + ML scan on bounded full-document text before swap commit."""
    if not records:
        return PolicyResult(action="allow", policy_version=scanner.version)

    rules = scanner._rules()
    patterns = list(rules.get("injection_patterns") or [])
    safety_patterns = list(rules.get("safety_critical_phrases") or [])
    document_type = str(document_context.get("document_type") or "")
    full_text = concat_records(records, max_chars=max_chars)

    findings: list[PolicyFinding] = []
    overlap = max(_max_pattern_length(patterns), 64)
    window = max(overlap * 2, 160)
    for window_text in sliding_windows(full_text, window=window, overlap=overlap):
        findings.extend(scan_injection_patterns(window_text, patterns))
        findings.extend(scan_safety_phrases(window_text, safety_patterns))
        if rules.get("secrets_scan"):
            findings.extend(scan_secrets(window_text))

    if ml_classifier_enabled():
        regex_hits = sum(1 for finding in findings if finding.resolved_category() == "injection")
        ml_score = await classify_risk(
            full_text,
            regex_finding_count=regex_hits,
            ocr_confidence_min=document_context.get("ocr_confidence_min"),
            document_type=document_type,
        )
        if ml_score is not None and ml_score >= _ML_RISK_THRESHOLD:
            findings.append(
                PolicyFinding(
                    rule_id="classifier_exemplar",
                    severity="high",
                    message=f"Exemplar classifier risk score {ml_score:.2f}",
                    category="ml",
                )
            )

    deduped = _dedupe_findings(findings)
    decision = decide(deduped, document_type, rules)
    action = decision_to_action(decision)
    risk_score = _risk_score(deduped)
    return PolicyResult(
        action=action,  # type: ignore[arg-type]
        findings=deduped,
        policy_version=scanner.version,
        risk_score=risk_score,
        decision=decision,
    )


async def scan_accumulator(
    accumulator: DocumentAccumulator,
    document_context: dict[str, Any],
    scanner: Any,
) -> PolicyResult:
    return await scan_full(accumulator.all_records(), document_context, scanner)


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


def _risk_score(findings: list[PolicyFinding]) -> float:
    if not findings:
        return 0.0
    weights = {"low": 0.2, "medium": 0.55, "high": 0.9, "critical": 1.0}
    return max(weights.get(f.severity, 0.0) for f in findings)


def has_critical_findings(result: PolicyResult) -> bool:
    return result.max_severity == FindingSeverity.CRITICAL
