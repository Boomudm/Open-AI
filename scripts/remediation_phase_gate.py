#!/usr/bin/env python3
"""Remediation phase release gate — contract tests, pytest, and eval subsets."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs" / "remediation"
EVAL_DIR = ROOT / "configs" / "eval"
GATES_PATH = CONFIG_DIR / "phase_gates.yaml"

PHASE_SUITE_MAP: dict[str, str] = {
    "2": "adversarial",
    "02": "adversarial",
    "6": "baseline_ci",
    "06": "baseline_ci",
    "8": "adversarial",
    "08": "adversarial",
    "9": "grounding",
    "09": "grounding",
    "12": "adversarial",
    "13": "adversarial",
}


def _normalize_phase(phase: str) -> str:
    stripped = phase.lstrip("0")
    return stripped or "0"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _load_phase_config(phase: str) -> dict[str, Any]:
    normalized = _normalize_phase(phase)
    candidates = [
        CONFIG_DIR / f"phase_{phase.zfill(2)}.yaml",
        CONFIG_DIR / f"phase_{normalized}.yaml",
        CONFIG_DIR / f"phase_{phase}.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return _load_yaml(path)
    return {}


def _load_phase_gates(phase: str) -> dict[str, Any]:
    gates_doc = _load_yaml(GATES_PATH)
    phases = gates_doc.get("phases") or {}
    normalized = _normalize_phase(phase)
    for key in (phase, phase.zfill(2), normalized, normalized.zfill(2)):
        entry = phases.get(str(key))
        if isinstance(entry, dict):
            return entry
    return {}


def _resolve_eval_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _parse_threshold(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise ValueError(f"Invalid threshold (expected key=value): {raw}")
    key, value = raw.split("=", 1)
    return key.strip(), float(value.strip())


def _run(cmd: list[str]) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _eval_cmd_for_config(
    config_path: Path,
    *,
    thresholds: dict[str, float] | None = None,
    require_answer_path: bool = False,
) -> list[str]:
    eval_doc = _load_yaml(config_path)
    if eval_doc.get("pytest") and not eval_doc.get("cases"):
        raise ValueError(f"Eval config {config_path} is pytest-only; use --pytest instead")

    cmd = [
        "uv",
        "run",
        "python",
        "scripts/evaluate_baseline.py",
        "--deterministic-rag",
        "--skip-requires-live-api",
        "--config",
        str(config_path),
    ]

    suite = eval_doc.get("suite")
    if suite in PHASE_SUITE_MAP.values() or suite in ("baseline", "heldout", "adversarial", "safety_critical"):
        cmd = [
            "uv",
            "run",
            "python",
            "scripts/evaluate_baseline.py",
            "--deterministic-rag",
            "--skip-requires-live-api",
            "--suite",
            str(suite),
        ]

    categories = {c.get("category") for c in (eval_doc.get("cases") or []) if isinstance(c, dict)}
    safety_cases = any(c.get("safety_critical") for c in (eval_doc.get("cases") or []) if isinstance(c, dict))
    if (
        require_answer_path
        or config_path.name in {"adversarial.yaml", "safety_critical.yaml"}
        or "loto_bypass" in categories
        or safety_cases
    ):
        cmd.append("--require-answer-path")

    if thresholds:
        for key, value in thresholds.items():
            cmd.extend(["--threshold", f"{key}={value}"])

    return cmd


def _eval_cmd_for_subset(eval_subset: str, phase_cfg: dict[str, Any]) -> list[str]:
    eval_path = CONFIG_DIR / f"eval_{eval_subset}.yaml"
    if not eval_path.is_file():
        raise FileNotFoundError(f"Eval subset config not found: {eval_path}")

    eval_doc = _load_yaml(eval_path)
    external_config = eval_doc.get("config")
    if external_config:
        config_path = _resolve_eval_path(str(external_config))
        thresholds = eval_doc.get("thresholds") or {}
        return _eval_cmd_for_config(
            config_path,
            thresholds=thresholds if isinstance(thresholds, dict) else None,
            require_answer_path=eval_subset in {"adversarial", "rag_safety"},
        )

    cases = eval_doc.get("cases") or []
    if cases:
        return _eval_cmd_for_config(eval_path, thresholds=eval_doc.get("thresholds"))

    suite = str(
        phase_cfg.get("eval_suite")
        or eval_doc.get("suite")
        or PHASE_SUITE_MAP.get(str(phase_cfg.get("phase", "")), "")
    )
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/evaluate_baseline.py",
        "--deterministic-rag",
        "--skip-requires-live-api",
    ]
    if suite:
        cmd.extend(["--suite", suite])
    else:
        cmd.extend(["--config", str(eval_path)])

    if suite in {"adversarial", "safety_critical"} or eval_subset in {"adversarial", "rag_safety"}:
        cmd.append("--require-answer-path")
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run remediation phase release gates")
    parser.add_argument("--phase", required=True, help="Phase number (e.g. 0, 00, 12)")
    parser.add_argument("--eval-subset", default=None, help="Legacy eval subset name (eval_*.yaml)")
    parser.add_argument(
        "--pytest",
        action="append",
        dest="pytest_paths",
        default=None,
        help="Additional pytest path(s) to run",
    )
    parser.add_argument(
        "--eval",
        action="append",
        dest="eval_configs",
        default=None,
        help="Eval YAML config path (repeatable)",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        dest="thresholds",
        default=None,
        help="Metric threshold override key=value (repeatable)",
    )
    args = parser.parse_args(argv)

    phase_cfg = _load_phase_config(args.phase)
    gate_cfg = _load_phase_gates(args.phase)

    threshold_overrides: dict[str, float] = {}
    for raw in args.thresholds or []:
        key, value = _parse_threshold(raw)
        threshold_overrides[key] = value
    yaml_thresholds = gate_cfg.get("thresholds") or {}
    if isinstance(yaml_thresholds, dict):
        for key, value in yaml_thresholds.items():
            threshold_overrides.setdefault(str(key), float(value))

    if gate_cfg.get("contract_tests", phase_cfg.get("contract_tests", True)):
        _run(["uv", "run", "pytest", "tests/contracts/", "-q", "--tb=short"])

    eval_configs: list[Path] = []
    for raw in args.eval_configs or []:
        eval_configs.append(_resolve_eval_path(raw))
    for key in ("eval", "eval_secondary"):
        raw = gate_cfg.get(key)
        if raw:
            eval_configs.append(_resolve_eval_path(str(raw)))

    eval_subset = args.eval_subset or phase_cfg.get("eval_subset")
    if eval_subset and not eval_configs:
        try:
            _run(_eval_cmd_for_subset(str(eval_subset), phase_cfg))
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        for config_path in eval_configs:
            if not config_path.is_file():
                print(f"Eval config not found: {config_path}", file=sys.stderr)
                return 1
            eval_doc = _load_yaml(config_path)
            if eval_doc.get("pytest") and not eval_doc.get("cases"):
                for pytest_path in eval_doc.get("pytest") or []:
                    _run(["uv", "run", "pytest", str(pytest_path), "-q", "--tb=short"])
                continue
            _run(
                _eval_cmd_for_config(
                    config_path,
                    thresholds=threshold_overrides or None,
                    require_answer_path=config_path.name in {"adversarial.yaml", "safety_critical.yaml"},
                )
            )

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

    print(f"Phase {args.phase} gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
