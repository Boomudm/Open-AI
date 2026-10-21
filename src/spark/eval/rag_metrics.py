"""RAGAS-style retrieval metrics for evaluation runs.

Computes aggregate context precision/recall and attribution accuracy from
``CaseScore`` rows produced by ``scripts/evaluate_baseline.py``.
"""

from __future__ import annotations

import re
from typing import Any, Protocol


class _RagScore(Protocol):
    mode: str
    passed: bool
    expected_sources: int
    returned_sources: int
    matched_sources: int
    issues: list[str]


def _pct(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 100.0
    return round((float(numerator) / float(denominator)) * 100, 2)


def _normalize_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9\u0E00-\u0E7F]+", text.casefold()) if token}


_THAI_CHAR_RE = re.compile(r"[฀-๿]")


def faithfulness(answer: str, cited_spans: list[str]) -> float | None:
    """Fraction of answer tokens supported by cited spans (0.0–1.0).

    Script-aware: a token whose script never occurs in the cited spans is
    untestable by token overlap — Thai prose summarizing an English manual
    span can never token-match it, and averaging in that structural 0.0 made
    the faithfulness gate unpassable for cross-lingual corpora. Such tokens
    are excluded from the denominator; the technical claims that survive
    translation (numbers, Latin identifiers/units) stay enforced. Returns
    ``None`` when no testable token remains, so callers skip the case rather
    than score it.
    """
    answer_tokens = _normalize_tokens(answer)
    if not answer_tokens:
        return 1.0
    cited_tokens: set[str] = set()
    for span in cited_spans:
        cited_tokens |= _normalize_tokens(span)
    if not cited_tokens:
        return 0.0
    spans_have_thai = any(_THAI_CHAR_RE.search(token) for token in cited_tokens)
    spans_have_latin = any(not _THAI_CHAR_RE.search(token) for token in cited_tokens)
    testable = {
        token
        for token in answer_tokens
        if (spans_have_thai if _THAI_CHAR_RE.search(token) else spans_have_latin)
    }
    if not testable:
        return None
    supported = testable & cited_tokens
    return round(len(supported) / len(testable), 4)


def context_recall(
    retrieved_chunk_ids: list[str],
    gold_chunk_ids: list[str],
) -> float:
    """Fraction of gold chunks present in retrieval (0.0–1.0)."""
    if not gold_chunk_ids:
        return 1.0
    retrieved = {str(chunk_id) for chunk_id in retrieved_chunk_ids}
    gold = {str(chunk_id) for chunk_id in gold_chunk_ids}
    if not gold:
        return 1.0
    return round(len(retrieved & gold) / len(gold), 4)


def compute_rag_metrics(results: list[_RagScore]) -> dict[str, Any]:
    """Aggregate RAG retrieval and attribution metrics for trending dashboards."""
    rag = [r for r in results if r.mode == "rag"]
    with_expected = [r for r in rag if r.expected_sources > 0]
    with_returned = [r for r in rag if r.returned_sources > 0]

    expected_total = sum(r.expected_sources for r in with_expected)
    returned_total = sum(r.returned_sources for r in with_returned)
    matched_total = sum(r.matched_sources for r in rag)

    forbidden_failures = sum(
        1 for r in rag if any("forbidden_sources_returned" in issue for issue in r.issues)
    )
    attribution_cases = [r for r in with_expected if r.passed or r.matched_sources > 0]
    attribution_pass = sum(
        1
        for r in attribution_cases
        if r.matched_sources >= r.expected_sources
        and not any("forbidden_sources_returned" in issue for issue in r.issues)
    )

    return {
        "rag_case_count": len(rag),
        "context_precision_pct": _pct(matched_total, returned_total),
        "context_recall_pct": _pct(matched_total, expected_total),
        "citation_accuracy_pct": _pct(matched_total, expected_total),
        "attribution_accuracy_pct": _pct(attribution_pass, len(attribution_cases)),
        "forbidden_source_violations": forbidden_failures,
    }


def per_document_type_breakdown(results: list[_RagScore]) -> dict[str, dict[str, Any]]:
    """Pass rate and retrieval stats grouped by expected ``document_type``."""
    buckets: dict[str, list[_RagScore]] = {}
    for row in results:
        if row.mode != "rag":
            continue
        output = getattr(row, "output", None) or {}
        sources = list(output.get("sources") or [])
        doc_types: set[str] = set()
        for source in sources:
            if isinstance(source, dict) and source.get("document_type"):
                doc_types.add(str(source["document_type"]))
        if not doc_types:
            doc_types.add("_none")
        for doc_type in doc_types:
            buckets.setdefault(doc_type, []).append(row)

    breakdown: dict[str, dict[str, Any]] = {}
    for doc_type, rows in sorted(buckets.items()):
        passed = sum(1 for r in rows if r.passed)
        breakdown[doc_type] = {
            "case_count": len(rows),
            "passed_cases": passed,
            "pass_pct": _pct(passed, len(rows)),
            "context_precision_pct": _pct(
                sum(r.matched_sources for r in rows),
                sum(r.returned_sources for r in rows if r.returned_sources),
            ),
            "context_recall_pct": _pct(
                sum(r.matched_sources for r in rows),
                sum(r.expected_sources for r in rows if r.expected_sources),
            ),
        }
    return breakdown
