"""Phase 13 — production_lock_v3 strict outcome validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_production_lock_v3.py"
LOCK = ROOT / "configs" / "eval" / "production_lock_v3.json"


def _run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_lock_v3_json_structure_passes() -> None:
    result = _run_validator("--lock", str(LOCK))
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK production lock v3" in result.stdout


def test_strict_requires_report_dir() -> None:
    result = _run_validator("--lock", str(LOCK), "--strict")
    assert result.returncode == 1
    assert "--strict requires --report-dir" in result.stderr


def test_strict_fails_on_missing_reports(tmp_path: Path) -> None:
    result = _run_validator(
        "--lock",
        str(LOCK),
        "--report-dir",
        str(tmp_path),
        "--strict",
    )
    assert result.returncode == 1
    assert "missing report" in result.stderr


def test_strict_fails_when_pass_rate_below_threshold(tmp_path: Path) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for suite_name in lock["required_suites"]:
        report = {
            "metrics": {
                "overall_case_pass_pct": 100.0,
                "citation_accuracy_pct": 100.0,
                "gate_case_count": 100,
                "case_count": 100,
            }
        }
        thresholds = lock["suites"][suite_name]
        if "overall_case_pass_pct" in thresholds:
            report["metrics"]["overall_case_pass_pct"] = 0.0
        if "citation_accuracy_pct" in thresholds:
            report["metrics"]["citation_accuracy_pct"] = 0.0
        (tmp_path / f"{suite_name}.json").write_text(
            json.dumps(report),
            encoding="utf-8",
        )

    result = _run_validator(
        "--lock",
        str(LOCK),
        "--report-dir",
        str(tmp_path),
        "--strict",
    )
    assert result.returncode == 1
    assert "below lock minimum" in result.stderr


def test_strict_passes_when_reports_meet_thresholds(tmp_path: Path) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for suite_name in lock["required_suites"]:
        thresholds = lock["suites"][suite_name]
        metrics: dict[str, float | int] = {"gate_case_count": 100, "case_count": 100}
        for key, minimum in thresholds.items():
            if key == "min_cases":
                metrics["gate_case_count"] = int(minimum)
                metrics["case_count"] = int(minimum)
            else:
                metrics[key] = float(minimum) + 1.0
        (tmp_path / f"{suite_name}.json").write_text(
            json.dumps({"metrics": metrics}),
            encoding="utf-8",
        )

    result = _run_validator(
        "--lock",
        str(LOCK),
        "--report-dir",
        str(tmp_path),
        "--strict",
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_heldout_min_cases_enforced(tmp_path: Path) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for suite_name in lock["required_suites"]:
        metrics: dict[str, float | int] = {
            "overall_case_pass_pct": 100.0,
            "citation_accuracy_pct": 100.0,
            "gate_case_count": 100,
            "case_count": 100,
        }
        if suite_name == "heldout":
            metrics["gate_case_count"] = 50
            metrics["case_count"] = 50
        (tmp_path / f"{suite_name}.json").write_text(
            json.dumps({"metrics": metrics}),
            encoding="utf-8",
        )

    result = _run_validator(
        "--lock",
        str(LOCK),
        "--report-dir",
        str(tmp_path),
        "--strict",
    )
    assert result.returncode == 1
    assert "heldout" in result.stderr
    assert "min_cases" in result.stderr
