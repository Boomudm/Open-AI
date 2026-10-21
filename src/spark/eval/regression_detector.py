"""Detect RAG quality regressions between two evaluation runs.

Compares two CI eval JSON reports and flags regressions.
Used in CI to compare current branch against main baseline.

Usage:
    python -m spark.eval.regression_detector --baseline reports/main_eval.json --current reports/ci_eval_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RegressionThresholds:
    faithfulness_drop: float = 0.05
    context_recall_drop: float = 0.05
    pass_rate_drop: float = 0.10
    latency_p95_increase_pct: float = 0.50


@dataclass
class RegressionReport:
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    passed: bool = True


def compare_reports(
    baseline: dict,
    current: dict,
    thresholds: RegressionThresholds | None = None,
) -> RegressionReport:
    t = thresholds or RegressionThresholds()
    report = RegressionReport()

    b_faith = baseline.get("avg_faithfulness", 0)
    c_faith = current.get("avg_faithfulness", 0)
    delta_faith = c_faith - b_faith
    if delta_faith < -t.faithfulness_drop:
        report.regressions.append(
            f"faithfulness dropped {b_faith:.2%} → {c_faith:.2%} (Δ{delta_faith:+.2%})"
        )
    elif delta_faith > t.faithfulness_drop:
        report.improvements.append(
            f"faithfulness improved {b_faith:.2%} → {c_faith:.2%} (Δ{delta_faith:+.2%})"
        )

    b_recall = baseline.get("avg_context_recall", 0)
    c_recall = current.get("avg_context_recall", 0)
    delta_recall = c_recall - b_recall
    if delta_recall < -t.context_recall_drop:
        report.regressions.append(
            f"context_recall dropped {b_recall:.2%} → {c_recall:.2%} (Δ{delta_recall:+.2%})"
        )
    elif delta_recall > t.context_recall_drop:
        report.improvements.append(
            f"context_recall improved {b_recall:.2%} → {c_recall:.2%} (Δ{delta_recall:+.2%})"
        )

    b_total = baseline.get("passed_cases", 0) + baseline.get("failed_cases", 1)
    c_total = current.get("passed_cases", 0) + current.get("failed_cases", 1)
    b_rate = baseline.get("passed_cases", 0) / max(b_total, 1)
    c_rate = current.get("passed_cases", 0) / max(c_total, 1)
    delta_rate = c_rate - b_rate
    if delta_rate < -t.pass_rate_drop:
        report.regressions.append(
            f"pass_rate dropped {b_rate:.1%} → {c_rate:.1%} (Δ{delta_rate:+.1%})"
        )

    b_p95 = baseline.get("latency_p95_ms", 0)
    c_p95 = current.get("latency_p95_ms", 0)
    if b_p95 > 0:
        latency_increase = (c_p95 - b_p95) / b_p95
        if latency_increase > t.latency_p95_increase_pct:
            report.regressions.append(
                f"p95 latency increased {b_p95:.0f}ms → {c_p95:.0f}ms (+{latency_increase:.0%})"
            )

    c_forbidden = current.get("forbidden_violations", 0)
    b_forbidden = baseline.get("forbidden_violations", 0)
    if c_forbidden > b_forbidden:
        report.regressions.append(
            f"forbidden_violations increased {b_forbidden} → {c_forbidden}"
        )

    report.passed = len(report.regressions) == 0
    return report


def format_regression_report(report: RegressionReport) -> str:
    lines = ["RAG Regression Analysis", "=" * 40]
    if report.regressions:
        lines.append("\nREGRESSIONS:")
        for r in report.regressions:
            lines.append(f"  ✗ {r}")
    if report.improvements:
        lines.append("\nIMPROVEMENTS:")
        for i in report.improvements:
            lines.append(f"  ✓ {i}")
    if not report.regressions and not report.improvements:
        lines.append("\n  No significant changes detected.")
    lines.append("")
    lines.append(f"Result: {'PASS' if report.passed else 'FAIL — regressions detected'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG regression detector")
    parser.add_argument("--baseline", required=True, help="Baseline eval JSON report")
    parser.add_argument("--current", required=True, help="Current eval JSON report")
    args = parser.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text())
    current = json.loads(Path(args.current).read_text())

    report = compare_reports(baseline, current)
    print(format_regression_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
