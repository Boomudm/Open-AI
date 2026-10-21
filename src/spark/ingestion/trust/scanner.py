"""Ingest trust boundary orchestrator — scan before embed."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.core.logging import get_logger
from spark.ingestion.parsers.base import ParsedRecord

from .classifier import classify_risk, ml_classifier_enabled
from .document_scan import concat_records
from .gate import decide, decision_to_action
from .models import FindingSeverity, PolicyFinding, PolicyResult
from .rules_injection import scan_injection_patterns, validate_injection_patterns
from .rules_safety import scan_safety_phrases
from .rules_secrets import scan_secrets
from .presidio_scanner import scan_pii

log = get_logger(__name__)

_POLICY_PATH = Path(__file__).resolve().parents[4] / "configs" / "ingest_content_policy.yaml"
_PERMISSIVE_PATH = Path(__file__).resolve().parents[4] / "configs" / "trust" / "policy_permissive.yaml"


def _policy_path() -> Path:
    from spark.core.config import settings

    if settings.spark_profile.strip().lower() == "test" and _PERMISSIVE_PATH.is_file():
        return _PERMISSIVE_PATH
    return _POLICY_PATH


@lru_cache(maxsize=1)
def load_content_policy() -> dict[str, Any]:
    path = _policy_path()
    if not path.is_file():
        raise FileNotFoundError(f"Content policy config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("ingest content policy must be a mapping")
    rules = data.get("rules") or {}
    if isinstance(rules, dict):
        validate_injection_patterns(list(rules.get("injection_patterns") or []))
        validate_injection_patterns(list(rules.get("safety_critical_phrases") or []))
    return data


def clear_policy_cache() -> None:
    load_content_policy.cache_clear()


def trust_scan_enabled() -> bool:
    """Production/dev always scan; test profile off unless explicitly enabled."""
    from spark.core.config import settings
    from spark.core.production_profile import ProductionProfile

    profile = settings.spark_profile.strip().lower()
    if profile in {"production", "dev"}:
        return True
    return ProductionProfile.from_settings().ingest_policy_enabled




class TrustScanner:
    """Document-level trust scan before vector indexing."""

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self._policy = policy or load_content_policy()

    @property
    def version(self) -> str:
        return str(self._policy.get("version") or "0")

    def _rules(self) -> dict[str, Any]:
        rules = self._policy.get("rules") or {}
        return rules if isinstance(rules, dict) else {}

    def scan_document(
        self,
        *,
        text: str,
        document_context: dict[str, Any],
        machine_specs: list[dict[str, Any]] | None = None,
    ) -> PolicyResult:
        del machine_specs  # numeric spec cross-check removed — findings are log-only now
        rules = self._rules()
        document_type = str(document_context.get("document_type") or "")

        findings: list[PolicyFinding] = []
        findings.extend(
            scan_injection_patterns(text, list(rules.get("injection_patterns") or []))
        )
        findings.extend(
            scan_safety_phrases(text, list(rules.get("safety_critical_phrases") or []))
        )
        if rules.get("secrets_scan"):
            findings.extend(scan_secrets(text))
        if rules.get("presidio_pii_scan", True):
            findings.extend(
                scan_pii(
                    text,
                    factory_id=str(document_context.get("factory_id") or "") or None,
                )
            )

        ocr_min = document_context.get("ocr_confidence_min")
        if ocr_min is not None and float(ocr_min) < 50.0:
            findings.append(
                PolicyFinding(
                    rule_id="ocr_low_confidence",
                    severity="low",
                    message="OCR confidence below 50% on at least one page",
                    category="ocr",
                )
            )

        decision = decide(findings, document_type, rules)
        action = decision_to_action(decision)
        risk_score = _risk_score(findings)

        if findings and action == "allow":
            log.info(
                "trust_findings_logged",
                document_type=document_type,
                finding_count=len(findings),
            )

        return PolicyResult(
            action=action,  # type: ignore[arg-type]
            findings=findings,
            policy_version=self.version,
            risk_score=risk_score,
            decision=decision,
        )

    async def scan_document_async(
        self,
        *,
        text: str,
        document_context: dict[str, Any],
        dry_run: bool = False,
    ) -> PolicyResult:
        if dry_run:
            return self.scan_document(text=text, document_context=document_context)
        result = self.scan_document(text=text, document_context=document_context)
        return await _apply_ml_classifier(
            result,
            text=text,
            document_context=document_context,
            rules=self._rules(),
        )

    def scan(
        self,
        *,
        text: str | None,
        payload: dict[str, Any],
        document_context: dict[str, Any],
    ) -> PolicyResult:
        """Chunk-level scan (policy rescan path)."""
        haystack = text or payload.get("page_content") or ""
        return self.scan_document(
            text=haystack,
            document_context={
                **document_context,
                "document_type": document_context.get("document_type")
                or payload.get("document_type"),
            },
        )

    async def scan_async(
        self,
        *,
        text: str | None,
        payload: dict[str, Any],
        document_context: dict[str, Any],
    ) -> PolicyResult:
        return self.scan(text=text, payload=payload, document_context=document_context)


# Back-compat alias used by rescan and tests.
ContentPolicyScanner = TrustScanner


def _risk_score(findings: list[PolicyFinding]) -> float:
    if not findings:
        return 0.0
    weights = {"low": 0.2, "medium": 0.55, "high": 0.9, "critical": 1.0}
    return max(weights.get(f.severity, 0.0) for f in findings)


_ML_RISK_THRESHOLD = 0.85


async def _apply_ml_classifier(
    result: PolicyResult,
    *,
    text: str,
    document_context: dict[str, Any],
    rules: dict[str, Any],
) -> PolicyResult:
    if not ml_classifier_enabled():
        return result
    regex_hits = sum(
        1 for finding in result.findings if finding.resolved_category() == "injection"
    )
    ml_score = await classify_risk(
        text,
        regex_finding_count=regex_hits,
        ocr_confidence_min=document_context.get("ocr_confidence_min"),
        document_type=str(document_context.get("document_type") or ""),
    )
    if ml_score is None or ml_score < _ML_RISK_THRESHOLD:
        return result
    result.findings.append(
        PolicyFinding(
            rule_id="classifier_exemplar",
            severity="high",
            message=f"Exemplar classifier risk score {ml_score:.2f}",
            category="ml",
        )
    )
    document_type = str(document_context.get("document_type") or "")
    decision = decide(result.findings, document_type, rules)
    result.decision = decision
    result.action = decision_to_action(decision)  # type: ignore[assignment]
    result.risk_score = max(result.risk_score, float(ml_score))
    return result


def merge_policy_results(
    results: list[PolicyResult],
    *,
    document_type: str,
    rules: dict[str, Any],
    policy_version: str,
) -> PolicyResult:
    """Aggregate per-record scans — worst severity wins, no text concatenation."""
    if not results:
        return PolicyResult(action="allow", policy_version=policy_version)

    findings: list[PolicyFinding] = []
    max_risk = 0.0
    for result in results:
        findings.extend(result.findings)
        max_risk = max(max_risk, result.risk_score)

    decision = decide(findings, document_type, rules)
    action = decision_to_action(decision)
    return PolicyResult(
        action=action,  # type: ignore[arg-type]
        findings=findings,
        policy_version=policy_version,
        risk_score=max_risk,
        decision=decision,
    )


async def scan_record(
    scanner: TrustScanner,
    record: ParsedRecord,
    document_context: dict[str, Any],
) -> PolicyResult:
    text = record.text_for_embedding or str(record.payload.get("page_content") or "")
    return await scanner.scan_document_async(text=text, document_context=document_context)


async def scan_batch(
    scanner: TrustScanner,
    records: list[ParsedRecord],
    document_context: dict[str, Any],
) -> PolicyResult:
    if not records:
        return PolicyResult(action="allow", policy_version=scanner.version)

    results: list[PolicyResult] = []
    rules = scanner._rules()
    document_type = str(document_context.get("document_type") or "")

    for record in records:
        result = await scan_record(scanner, record, document_context)
        if result.action == "block" or result.max_severity == FindingSeverity.CRITICAL:
            return result
        results.append(result)

    merged = merge_policy_results(
        results,
        document_type=document_type,
        rules=rules,
        policy_version=scanner.version,
    )

    if ml_classifier_enabled():
        batch_text = concat_records(records)
        merged = await _apply_ml_classifier(
            merged,
            text=batch_text,
            document_context=document_context,
            rules=rules,
        )
    return merged


trust_scanner = TrustScanner()
content_policy_scanner = trust_scanner
