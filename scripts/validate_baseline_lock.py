#!/usr/bin/env python3
"""Validate evaluation baseline lock files and optional fresh eval reports.

Tier 1 (dev, no API server): configs/evaluation_baseline_lock_no_api.json — min 91.67% gate pass (60 cases).
Tier 1 full (with live API): configs/evaluation_baseline_lock.json — min 87.88%.
Tier 2 (production merge): configs/evaluation_baseline_lock_production.json — min 90.91%.

Usage:
  # Static lock integrity (CI / go-live)
  python scripts/validate_baseline_lock.py --lock configs/evaluation_baseline_lock_production.json

  # Compare a fresh eval report against the lock regression bar
  python scripts/validate_baseline_lock.py \\
    --lock configs/evaluation_baseline_lock_production.json \\
    --report /tmp/eval-report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TIER_DEFAULTS: dict[str, dict[str, Any]] = {
    "tier1": {
        "lock": "configs/evaluation_baseline_lock_no_api.json",
        "min_pass_pct": 91.67,
        "production_equivalent": False,
    },
    "tier1_full": {
        "lock": "configs/evaluation_baseline_lock.json",
        "min_pass_pct": 87.88,
        "production_equivalent": False,
    },
    "tier2": {
        "lock": "configs/evaluation_baseline_lock_production.json",
        "min_pass_pct": 90.91,
        "production_equivalent": True,
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _resolve_min_pass_pct(lock: dict[str, Any], override: float | None) -> float:
    if override is not None:
        return override
    meta = lock.get("run_metadata") or {}
    bar = meta.get("regression_bar_overall_case_pass_pct")
    if bar is None:
        raise ValueError("Lock file missing run_metadata.regression_bar_overall_case_pass_pct")
    return float(bar)


def _infer_tier(lock_path: Path, lock: dict[str, Any]) -> str | None:
    name = lock_path.name
    if name == TIER_DEFAULTS["tier2"]["lock"].split("/")[-1]:
        return "tier2"
    if name == TIER_DEFAULTS["tier1"]["lock"].split("/")[-1]:
        return "tier1"
    meta = lock.get("run_metadata") or {}
    if meta.get("production_equivalent") is True:
        return "tier2"
    if meta.get("production_equivalent") is False:
        return "tier1"
    return None


def validate_lock(
    lock_path: Path,
    *,
    min_pass_pct: float | None = None,
    report_path: Path | None = None,
) -> None:
    lock = _load_json(lock_path)
    tier = _infer_tier(lock_path, lock)
    tier_defaults = TIER_DEFAULTS.get(tier or "", {})

    expected_min = min_pass_pct
    if expected_min is None and tier_defaults:
        expected_min = float(tier_defaults["min_pass_pct"])
    bar = _resolve_min_pass_pct(lock, expected_min)

    meta = lock.get("run_metadata") or {}
    metrics = lock.get("metrics") or {}

    if tier_defaults:
        expected_prod = tier_defaults["production_equivalent"]
        actual_prod = meta.get("production_equivalent")
        if actual_prod is not None and actual_prod != expected_prod:
            raise ValueError(
                f"{lock_path}: production_equivalent={actual_prod!r}, "
                f"expected {expected_prod!r} for {tier}"
            )

    locked_bar = float(meta.get("regression_bar_overall_case_pass_pct", bar))
    if abs(locked_bar - bar) > 0.01:
        raise ValueError(
            f"{lock_path}: regression bar {locked_bar}% does not match expected minimum {bar}%"
        )

    locked_pass = float(metrics.get("overall_case_pass_pct", 0))
    if locked_pass + 1e-9 < bar:
        raise ValueError(
            f"{lock_path}: locked metrics {locked_pass}% below regression bar {bar}%"
        )

    print(f"OK lock {lock_path}: regression_bar={bar}% locked_pass={locked_pass}% tier={tier or 'unknown'}")

    if report_path is None:
        return

    report = _load_json(report_path)
    report_metrics = report.get("metrics") or {}
    report_pass = float(report_metrics.get("overall_case_pass_pct", 0))
    if report_pass + 1e-9 < bar:
        raise ValueError(
            f"Report {report_path}: overall_case_pass_pct {report_pass}% "
            f"below regression bar {bar}% (lock {lock_path})"
        )
    print(f"OK report {report_path}: overall_case_pass_pct={report_pass}% >= {bar}%")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate baseline lock files and eval reports")
    parser.add_argument(
        "--lock",
        type=Path,
        required=True,
        help="Path to evaluation_baseline_lock*.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional fresh eval JSON to compare against the lock regression bar",
    )
    parser.add_argument(
        "--min-pass-pct",
        type=float,
        default=None,
        help="Override minimum gate pass %% (default: from lock or tier — 87.88 dev, 90.91 production)",
    )
    parser.add_argument(
        "--tier",
        choices=("tier1", "tier2"),
        default=None,
        help="Tier preset when lock metadata is ambiguous",
    )
    args = parser.parse_args()

    min_pct = args.min_pass_pct
    if min_pct is None and args.tier:
        min_pct = float(TIER_DEFAULTS[args.tier]["min_pass_pct"])

    try:
        validate_lock(args.lock, min_pass_pct=min_pct, report_path=args.report)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
