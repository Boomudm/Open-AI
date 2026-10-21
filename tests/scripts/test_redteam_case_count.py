"""Phase 15 — red-team adversarial suite size and categories."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _count_cases() -> int:
    path = ROOT / "configs" / "eval" / "adversarial.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = list(raw.get("cases") or [])
    configs_root = ROOT / "configs"
    for item in raw.get("includes") or []:
        inc_path = configs_root / Path(str(item))
        inc_raw = yaml.safe_load(inc_path.read_text(encoding="utf-8")) or {}
        cases.extend(list(inc_raw.get("cases") or []))
    return len(cases)


def test_adversarial_suite_has_at_least_fifty_cases() -> None:
    assert _count_cases() >= 50


def test_validate_redteam_suite_script_passes() -> None:
    script = ROOT / "scripts" / "validate_redteam_suite.py"
    result = subprocess.run(
        [sys.executable, str(script), "--min-cases", "50"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_pilot_profile_exists() -> None:
    assert (ROOT / "configs" / "load" / "pilot_profile.yaml").is_file()
    assert (ROOT / "docs" / "runbooks" / "templates" / "pilot_soak_signoff.md").is_file()
