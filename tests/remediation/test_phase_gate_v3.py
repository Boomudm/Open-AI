"""Remediation blueprint v3 phase gate scaffolding (Phase 0)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_cutover_checklist_v3_published() -> None:
    checklist = ROOT / "docs" / "runbooks" / "cutover_checklist_v3.md"
    assert checklist.is_file()
    text = checklist.read_text(encoding="utf-8")
    assert "production_lock_v3" in text
    assert "full_reingest_v2_sparse.py" in text


def test_phase_gates_v3_yaml_exists_with_all_phases() -> None:
    path = ROOT / "configs" / "remediation" / "phase_gates_v3.yaml"
    assert path.is_file()
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    phases = doc.get("phases") or {}
    for phase_num in range(17):
        assert str(phase_num) in phases, f"missing phase {phase_num} in phase_gates_v3.yaml"


def test_phase_gates_v3_phase_zero_has_pytest_entries() -> None:
    path = ROOT / "configs" / "remediation" / "phase_gates_v3.yaml"
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    phase0 = (doc.get("phases") or {}).get("0") or {}
    pytest_paths = phase0.get("pytest") or []
    assert "tests/remediation/test_phase_gate_v3.py" in pytest_paths
    assert "tests/remediation/test_constitution_v3.py" in pytest_paths


def test_remediation_v3_phase_gate_script_exists() -> None:
    script = ROOT / "scripts" / "remediation_v3_phase_gate.py"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "phase_gates_v3.yaml" in text
    assert "--strict" in text
