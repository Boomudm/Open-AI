"""Phase 13 — production_lock_v3.json regression guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_lock_v3_json_exists() -> None:
    path = ROOT / "configs" / "eval" / "production_lock_v3.json"
    assert path.is_file()


def test_production_lock_v3_required_suites() -> None:
    path = ROOT / "configs" / "eval" / "production_lock_v3.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("version") == 3
    required = data.get("required_suites") or []
    for name in ("baseline_ci", "adversarial", "safety_critical", "grounding", "heldout"):
        assert name in required
    heldout = (data.get("suites") or {}).get("heldout") or {}
    assert int(heldout.get("min_cases") or 0) >= 100


def test_validate_production_lock_v3_script_passes() -> None:
    script = ROOT / "scripts" / "validate_production_lock_v3.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_v1_eval_lock_files_removed() -> None:
    assert not (ROOT / "configs" / "eval" / "production_lock.json").is_file()
    assert not (ROOT / "configs" / "evaluation_baseline_lock_production.json").is_file()


def test_phase_gates_v3_includes_phase_13() -> None:
    import yaml

    path = ROOT / "configs" / "remediation" / "phase_gates_v3.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    phases = data.get("phases") or {}
    assert "13" in phases
    entry = phases["13"]
    pytest_paths = entry.get("pytest") or []
    assert pytest_paths
