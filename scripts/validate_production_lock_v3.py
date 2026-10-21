#!/usr/bin/env python3
"""Validate configs/eval/production_lock_v3.json and enforce eval report outcomes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "configs" / "eval" / "production_lock_v3.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def validate_production_lock_v3(lock: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, float]]]:
    if int(lock.get("version", 0)) != 3:
        raise ValueError("production_lock_v3.json version must be 3")
    suites = lock.get("suites")
    if not isinstance(suites, dict) or not suites:
        raise ValueError("production_lock_v3.json missing suites mapping")
    required = lock.get("required_suites")
    if not isinstance(required, list) or not required:
        required = list(suites.keys())
    required_names = [str(name) for name in required]
    parsed: dict[str, dict[str, float | int]] = {}
    for suite_name, thresholds in suites.items():
        if not isinstance(thresholds, dict) or not thresholds:
            raise ValueError(f"Suite {suite_name!r} must have threshold mapping")
        parsed[suite_name] = {str(k): thresholds[k] for k in thresholds}
    missing = set(required_names) - set(parsed)
    if missing:
        raise ValueError(f"production_lock_v3.json missing required suites: {sorted(missing)}")
    return required_names, parsed  # type: ignore[return-value]


def _report_meets_thresholds(
    report: dict[str, Any],
    thresholds: dict[str, float | int],
    *,
    suite_name: str,
) -> list[str]:
    errors: list[str] = []
    metrics = report.get("metrics") or {}
    min_cases = thresholds.get("min_cases")
    if min_cases is not None:
        actual_cases = int(metrics.get("gate_case_count") or metrics.get("case_count") or 0)
        if actual_cases < int(min_cases):
            errors.append(
                f"{suite_name}: case_count={actual_cases} below min_cases={int(min_cases)}"
            )
    for key, minimum in thresholds.items():
        if key == "min_cases":
            continue
        if key not in metrics:
            errors.append(f"{suite_name}: report missing metric {key!r}")
            continue
        actual = float(metrics[key])
        if actual + 1e-9 < float(minimum):
            errors.append(
                f"{suite_name}: {key}={actual:.2f} below lock minimum {float(minimum):.2f}"
            )
    return errors


def validate_report_dir(
    *,
    report_dir: Path,
    required_suites: list[str],
    suites: dict[str, dict[str, float | int]],
) -> list[str]:
    errors: list[str] = []
    for suite_name in required_suites:
        report_path = report_dir / f"{suite_name}.json"
        if not report_path.is_file():
            errors.append(f"missing report: {report_path}")
            continue
        report = _load_json(report_path)
        errors.extend(
            _report_meets_thresholds(
                report,
                suites[suite_name],
                suite_name=suite_name,
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production_lock_v3.json and eval reports")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory of eval JSON reports named {suite}.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require --report-dir and fail on missing reports or threshold breaches",
    )
    args = parser.parse_args()

    try:
        lock = _load_json(args.lock)
        required_suites, suites = validate_production_lock_v3(lock)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK production lock v3: {args.lock} ({len(suites)} suites)")

    if args.strict and args.report_dir is None:
        print("FAIL: --strict requires --report-dir", file=sys.stderr)
        return 1

    if args.report_dir is None:
        return 0

    if not args.report_dir.is_dir():
        print(f"FAIL: report dir not found: {args.report_dir}", file=sys.stderr)
        return 1

    errors = validate_report_dir(
        report_dir=args.report_dir,
        required_suites=required_suites,
        suites=suites,
    )
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    for suite_name in required_suites:
        print(f"OK report {suite_name}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
