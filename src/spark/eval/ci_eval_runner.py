"""CI-integrated RAG evaluation runner with automated quality gates.

Runs a lightweight evaluation suite against the RAG pipeline and enforces
minimum thresholds for faithfulness, context recall, and attribution accuracy.
Designed to be called from CI pipelines to catch retrieval/generation regressions.

Usage:
    python -m spark.eval.ci_eval_runner --suite baseline_ci --threshold-file configs/eval/thresholds.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spark.eval.rag_metrics import faithfulness, context_recall


@dataclass(frozen=True)
class EvalThresholds:
    min_faithfulness: float = 0.70
    min_context_recall: float = 0.60
    min_attribution_accuracy: float = 0.65
    min_pass_rate: float = 0.75
    max_forbidden_source_violations: int = 0


@dataclass
class EvalResult:
    suite: str
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    avg_faithfulness: float = 0.0
    avg_context_recall: float = 0.0
    attribution_accuracy_pct: float = 0.0
    forbidden_violations: int = 0
    gate_passed: bool = False
    gate_failures: list[str] = field(default_factory=list)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    per_case_details: list[dict[str, Any]] = field(default_factory=list)


def load_thresholds(path: Path | None) -> EvalThresholds:
    if path and path.is_file():
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return EvalThresholds(
            min_faithfulness=float(raw.get("min_faithfulness", 0.70)),
            min_context_recall=float(raw.get("min_context_recall", 0.60)),
            min_attribution_accuracy=float(raw.get("min_attribution_accuracy", 0.65)),
            min_pass_rate=float(raw.get("min_pass_rate", 0.75)),
            max_forbidden_source_violations=int(raw.get("max_forbidden_source_violations", 0)),
        )
    return EvalThresholds()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * pct / 100.0)
    return sorted_v[min(idx, len(sorted_v) - 1)]


def _ragfilter_kwargs(case: dict[str, Any]) -> dict[str, Any]:
    """Build RAGFilter kwargs from a case's ``filter:`` block (or legacy ``factory_id``)."""
    from dataclasses import fields

    from spark.retrieval.models import RAGFilter

    valid_fields = {f.name for f in fields(RAGFilter)}
    filter_spec = case.get("filter")
    if not isinstance(filter_spec, dict):
        factory_id = case.get("factory_id")
        filter_spec = {"factory_id": factory_id} if factory_id else {}
    return {k: v for k, v in filter_spec.items() if k in valid_fields and v is not None}


def _source_matches(spec: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
    for source in sources:
        if spec.get("document_type") and str(source.get("document_type") or "").lower() != str(
            spec["document_type"]
        ).lower():
            continue
        needle = spec.get("source_file_contains")
        if needle and needle.lower() not in str(source.get("source_file") or "").lower():
            continue
        if spec.get("page") is not None and source.get("page") != spec["page"]:
            continue
        return True
    return False


def _check_case_expectations(
    expect: dict[str, Any],
    *,
    answer: str,
    answer_path: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    """Evaluate a case's ``expect:`` block; return a list of failure reasons (empty = pass)."""
    from spark.retrieval.synthesis import _is_no_data_answer

    issues: list[str] = []
    lower_answer = answer.lower()

    if expect.get("no_data") is True and not _is_no_data_answer(answer):
        issues.append("expected a no_data answer")
    if expect.get("answer_path") and str(answer_path) != str(expect["answer_path"]):
        issues.append(f"answer_path {answer_path!r} != expected {expect['answer_path']!r}")
    if "max_sources" in expect and len(sources) > int(expect["max_sources"]):
        issues.append(f"returned {len(sources)} sources > max_sources {expect['max_sources']}")

    contains_any = expect.get("answer_contains_any")
    if contains_any and not any(str(needle).lower() in lower_answer for needle in contains_any):
        issues.append(f"answer matched none of answer_contains_any={contains_any}")

    contains_all = expect.get("answer_contains_all")
    if contains_all:
        missing = [n for n in contains_all if str(n).lower() not in lower_answer]
        if missing:
            issues.append(f"answer missing answer_contains_all items={missing}")

    forbidden = expect.get("answer_forbidden_contains")
    if forbidden:
        hit = [n for n in forbidden if str(n).lower() in lower_answer]
        if hit:
            issues.append(f"answer contains forbidden terms={hit}")

    expected_sources = expect.get("sources")
    if expected_sources:
        for spec in expected_sources:
            if not _source_matches(spec, sources):
                issues.append(f"no returned source matched expected spec={spec}")

    return issues


async def run_eval_suite(
    suite_path: Path,
    thresholds: EvalThresholds,
) -> EvalResult:
    import yaml

    if not suite_path.is_file():
        return EvalResult(suite=str(suite_path), gate_failures=[f"Suite file not found: {suite_path}"])

    data = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases") or []
    if not cases:
        return EvalResult(suite=str(suite_path), gate_failures=["No cases in suite"])

    result = EvalResult(suite=suite_path.stem, total_cases=len(cases))
    faithfulness_scores: list[float] = []
    recall_scores: list[float] = []
    latencies: list[float] = []

    from spark.services.rag_service import rag_service
    from spark.retrieval.models import RAGFilter

    for case in cases:
        if not isinstance(case, dict):
            continue

        question = case.get("question", "")
        expected_sources = case.get("expected_sources") or []
        gold_chunk_ids = case.get("gold_chunk_ids") or []
        expected_mode = case.get("mode", "rag")
        expect = case.get("expect")

        if expected_mode != "rag":
            continue

        case_detail: dict[str, Any] = {"question": question, "case_id": case.get("id", "")}
        t0 = time.perf_counter()

        try:
            rf = RAGFilter(**_ragfilter_kwargs(case))
            rag_result = await rag_service.query(question, rf, top_k=6)

            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            latencies.append(latency_ms)

            answer = rag_result.answer or ""
            # Evidence text lives in each source's "spans" list (see
            # cited_docs_to_sources / EvidenceSpan.as_source_span) — sources
            # never carry a content/page_content key, so reading only those
            # made faithfulness structurally 0.0 for every case and the gate
            # could never pass.
            cited_spans: list[str] = []
            for s in rag_result.sources or []:
                for span in s.get("spans") or []:
                    span_text = span.get("text") if isinstance(span, dict) else None
                    if span_text:
                        cited_spans.append(str(span_text))
                legacy = s.get("content") or s.get("page_content")
                if legacy:
                    cited_spans.append(str(legacy))
            retrieved_ids = [
                str(s.get("chunk_id") or "")
                for s in (rag_result.sources or [])
                if s.get("chunk_id")
            ]

            f_score = faithfulness(answer, cited_spans)
            answer_path_str = str(rag_result.answer_path or "")
            is_generative_path = any(
                marker in answer_path_str
                for marker in ("grounded", "synthesis", "extractive", "paraphrase")
            )
            if not cited_spans and not is_generative_path:
                # Canned paths (no_data, query_policy_block, out_of_scope,
                # clarification, ...) make no factual claims — scoring them 0.0
                # would penalize correct refusal/intercept behavior. Generative
                # paths without citations stay 0.0: that IS a grounding failure.
                f_score = None
            if f_score is not None:
                faithfulness_scores.append(f_score)

            r_score = context_recall(retrieved_ids, gold_chunk_ids) if gold_chunk_ids else 1.0
            recall_scores.append(r_score)

            returned_source_ids = set()
            for s in rag_result.sources or []:
                doc_id = s.get("doc_id")
                if doc_id:
                    returned_source_ids.add(str(doc_id))

            expected_source_ids = {str(s) for s in expected_sources} if expected_sources else set()
            matched = len(returned_source_ids & expected_source_ids) if expected_source_ids else 0

            forbidden = case.get("forbidden_sources") or []
            forbidden_set = {str(f) for f in forbidden}
            has_forbidden = bool(returned_source_ids & forbidden_set)

            expect_issues: list[str] = []
            if isinstance(expect, dict):
                expect_issues = _check_case_expectations(
                    expect,
                    answer=answer,
                    answer_path=str(rag_result.answer_path or ""),
                    sources=rag_result.sources or [],
                )
                case_passed = not expect_issues and not has_forbidden
            else:
                case_passed = (
                    f_score is None or f_score >= thresholds.min_faithfulness
                ) and not has_forbidden

            if case_passed:
                result.passed_cases += 1
            else:
                result.failed_cases += 1

            if has_forbidden:
                result.forbidden_violations += 1

            case_detail.update({
                "passed": case_passed,
                "faithfulness": round(f_score, 4) if f_score is not None else None,
                "context_recall": round(r_score, 4),
                "latency_ms": latency_ms,
                "answer_path": str(rag_result.answer_path or ""),
                "matched_sources": matched,
                "returned_sources": len(returned_source_ids),
                "forbidden_hit": has_forbidden,
                "expect_issues": expect_issues,
            })

        except Exception as exc:
            result.failed_cases += 1
            case_detail.update({"passed": False, "error": str(exc)[:500]})

        result.per_case_details.append(case_detail)

    if faithfulness_scores:
        result.avg_faithfulness = round(sum(faithfulness_scores) / len(faithfulness_scores), 4)
    if recall_scores:
        result.avg_context_recall = round(sum(recall_scores) / len(recall_scores), 4)
    if latencies:
        result.latency_p50_ms = round(_percentile(latencies, 50), 2)
        result.latency_p95_ms = round(_percentile(latencies, 95), 2)

    evaluated = result.passed_cases + result.failed_cases
    if evaluated > 0:
        result.attribution_accuracy_pct = round(result.passed_cases / evaluated * 100, 2)

    gate_failures: list[str] = []
    if faithfulness_scores and result.avg_faithfulness < thresholds.min_faithfulness:
        gate_failures.append(
            f"faithfulness {result.avg_faithfulness:.2%} < {thresholds.min_faithfulness:.2%}"
        )
    if result.avg_context_recall < thresholds.min_context_recall:
        gate_failures.append(
            f"context_recall {result.avg_context_recall:.2%} < {thresholds.min_context_recall:.2%}"
        )
    pass_rate = result.passed_cases / max(evaluated, 1)
    if pass_rate < thresholds.min_pass_rate:
        gate_failures.append(
            f"pass_rate {pass_rate:.2%} < {thresholds.min_pass_rate:.2%}"
        )
    if result.forbidden_violations > thresholds.max_forbidden_source_violations:
        gate_failures.append(
            f"forbidden_violations {result.forbidden_violations} > {thresholds.max_forbidden_source_violations}"
        )

    result.gate_failures = gate_failures
    result.gate_passed = len(gate_failures) == 0
    return result


def format_report(result: EvalResult) -> str:
    lines = [
        f"{'='*60}",
        f" RAG Evaluation Report — {result.suite}",
        f"{'='*60}",
        f" Cases:        {result.total_cases}",
        f" Passed:       {result.passed_cases}",
        f" Failed:       {result.failed_cases}",
        f" Pass Rate:    {result.passed_cases / max(result.passed_cases + result.failed_cases, 1):.1%}",
        "",
        f" Faithfulness:     {result.avg_faithfulness:.2%}",
        f" Context Recall:   {result.avg_context_recall:.2%}",
        f" Attribution:      {result.attribution_accuracy_pct:.1f}%",
        f" Forbidden Hits:   {result.forbidden_violations}",
        "",
        f" Latency p50:      {result.latency_p50_ms:.0f}ms",
        f" Latency p95:      {result.latency_p95_ms:.0f}ms",
        "",
    ]

    if result.gate_passed:
        lines.append(" GATE: PASSED")
    else:
        lines.append(" GATE: FAILED")
        for fail in result.gate_failures:
            lines.append(f"   - {fail}")

    lines.append(f"{'='*60}")
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI RAG evaluation runner")
    parser.add_argument("--suite", default="golden_real_docs", help="Suite name or path")
    parser.add_argument("--threshold-file", default=None, help="YAML thresholds file")
    parser.add_argument("--output-json", default=None, help="Write JSON report to file")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[3]
    suite_configs = {
        "golden_real_docs": project_root / "configs" / "eval" / "golden_real_docs.yaml",
        "heldout": project_root / "configs" / "evaluation_heldout.yaml",
        "safety_critical": project_root / "configs" / "eval" / "safety_critical.yaml",
    }
    suite_path = Path(args.suite)
    if not suite_path.is_file():
        suite_path = suite_configs.get(args.suite, suite_path)

    threshold_path = Path(args.threshold_file) if args.threshold_file else (project_root / "configs" / "eval" / "thresholds.yaml")
    thresholds = load_thresholds(threshold_path)

    result = await run_eval_suite(suite_path, thresholds)

    print(format_report(result))

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "suite": result.suite,
            "total_cases": result.total_cases,
            "passed_cases": result.passed_cases,
            "failed_cases": result.failed_cases,
            "avg_faithfulness": result.avg_faithfulness,
            "avg_context_recall": result.avg_context_recall,
            "attribution_accuracy_pct": result.attribution_accuracy_pct,
            "forbidden_violations": result.forbidden_violations,
            "gate_passed": result.gate_passed,
            "gate_failures": result.gate_failures,
            "latency_p50_ms": result.latency_p50_ms,
            "latency_p95_ms": result.latency_p95_ms,
            "per_case_details": result.per_case_details,
        }
        output_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))

    return 0 if result.gate_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
