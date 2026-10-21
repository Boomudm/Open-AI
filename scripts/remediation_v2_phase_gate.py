#!/usr/bin/env python3
"""Remediation blueprint v2 phase release gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATES_PATH = ROOT / "configs" / "remediation" / "phase_gates_v2.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _normalize_phase(phase: str) -> str:
    stripped = phase.lstrip("0")
    return stripped or "0"


def _load_phase_gates(phase: str) -> dict[str, Any]:
    gates_doc = _load_yaml(GATES_PATH)
    phases = gates_doc.get("phases") or {}
    for key in (phase, phase.zfill(2), _normalize_phase(phase), _normalize_phase(phase).zfill(2)):
        entry = phases.get(str(key))
        if isinstance(entry, dict):
            return entry
    return {}


def _run(cmd: list[str]) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _run_eval_suite(entry: str | dict[str, Any]) -> None:
    if isinstance(entry, str):
        config_path = entry
        thresholds: dict[str, float] = {}
        suite_arg: list[str] = []
    else:
        config_path = str(entry.get("config") or entry.get("suite") or "")
        thresholds = {
            str(k): float(v) for k, v in (entry.get("thresholds") or {}).items()
        }
        suite_arg = []

    if not config_path:
        raise ValueError("eval entry missing config path")

    config = ROOT / config_path
    if not config.is_file():
        raise FileNotFoundError(f"Eval config not found: {config}")

    cmd = [
        "uv",
        "run",
        "python",
        "scripts/evaluate_baseline.py",
        "--config",
        str(config.relative_to(ROOT)),
        "--deterministic-rag",
        "--skip-requires-live-api",
    ]
    if config_path.endswith("adversarial.yaml") or config_path.endswith("safety_critical.yaml"):
        cmd.append("--require-answer-path")
    for key, value in thresholds.items():
        cmd.extend(["--threshold", f"{key}={value}"])
    cmd.extend(suite_arg)
    _run(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run remediation blueprint v2 phase gates")
    parser.add_argument("--phase", required=True, help="Phase number (e.g. 0, 00)")
    parser.add_argument(
        "--pytest",
        action="append",
        dest="pytest_paths",
        default=None,
        help="Additional pytest path(s)",
    )
    parser.add_argument(
        "--eval",
        action="append",
        dest="eval_configs",
        default=None,
        help="Eval config path (repeatable); use key=value via --threshold",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        dest="threshold_overrides",
        default=None,
        help="Threshold override suite_key=metric=value applied to all --eval runs",
    )
    parser.add_argument(
        "--skip-contracts",
        action="store_true",
        help="Skip tests/contracts/ suite",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip eval suite runs from phase_gates_v2.yaml",
    )
    args = parser.parse_args(argv)

    gate_cfg = _load_phase_gates(args.phase)
    if not gate_cfg and not args.pytest_paths and not args.eval_configs:
        print(
            f"No phase_gates_v2 entry for phase {args.phase} in {GATES_PATH}",
            file=sys.stderr,
        )
        return 1

    manifest = ROOT / "configs" / "production_lock_v2.yaml"
    if not manifest.is_file():
        print(f"Missing production lock manifest: {manifest}", file=sys.stderr)
        return 1

    lock_v3 = ROOT / "configs" / "eval" / "production_lock_v3.json"
    if int(args.phase) >= 15 and not lock_v3.is_file():
        print(f"Missing eval production lock: {lock_v3}", file=sys.stderr)
        return 1

    if int(args.phase) >= 15:
        _run(["uv", "run", "python", "scripts/validate_production_lock_v3.py", "--lock", str(lock_v3)])

    if gate_cfg.get("contract_tests", True) and not args.skip_contracts:
        _run(["uv", "run", "pytest", "tests/contracts/", "-q", "--tb=short"])

    pytest_paths: list[str] = []
    for source in (gate_cfg.get("pytest"), args.pytest_paths):
        if not source:
            continue
        if isinstance(source, str):
            pytest_paths.append(source)
        else:
            pytest_paths.extend(str(item) for item in source)

    for pytest_path in pytest_paths:
        _run(["uv", "run", "pytest", pytest_path, "-q", "--tb=short"])

    eval_entries: list[str | dict[str, Any]] = []
    if gate_cfg.get("eval"):
        raw_eval = gate_cfg.get("eval")
        if isinstance(raw_eval, list):
            eval_entries.extend(raw_eval)
    if args.eval_configs:
        cli_thresholds: dict[str, float] = {}
        for raw in args.threshold_overrides or []:
            if "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            cli_thresholds[key.strip()] = float(value.strip())
        for config_path in args.eval_configs:
            entry: dict[str, Any] = {"config": config_path}
            if cli_thresholds:
                entry["thresholds"] = cli_thresholds
            eval_entries.append(entry)

    for entry in eval_entries:
        if not args.skip_eval:
            _run_eval_suite(entry)

    print(f"Remediation v2 phase {args.phase} gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
