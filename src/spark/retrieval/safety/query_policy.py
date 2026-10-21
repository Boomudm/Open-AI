"""Query-side injection policy (Phase 10 — YAML blocklist)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spark.ingestion.trust.rules_injection import scan_injection_patterns
from spark.retrieval.safety.query_blocklist import load_query_blocklist_patterns
from spark.retrieval.common import log

QueryPolicyAction = Literal["allow", "block"]


@dataclass(frozen=True)
class QueryPolicyResult:
    action: QueryPolicyAction
    reason: str | None = None
    answer_path: str | None = None
    category: str | None = None


def _category_for_rule(rule_id: str) -> str | None:
    prefix = (rule_id or "").split(":", 1)[0]
    if prefix == "injection_patterns":
        return "injection"
    return None


def scan_query(question: str) -> QueryPolicyResult:
    """Block high-severity instruction override patterns before retrieval."""
    patterns = list(load_query_blocklist_patterns())
    findings = scan_injection_patterns(question, patterns)
    if findings:
        finding = findings[0]
        log.info(
            "query_policy_block",
            reason=finding.message,
            rule_id=finding.rule_id,
            question=(question or "")[:120],
        )
        return QueryPolicyResult(
            action="block",
            reason=finding.message,
            answer_path="query_policy_block",
            category=_category_for_rule(finding.rule_id),
        )
    return QueryPolicyResult(action="allow")
