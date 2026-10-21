#!/usr/bin/env python3
"""Application-layer remediation phase gate (v1 + v2 manifests)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATES_PATH = ROOT / "configs" / "app_layer" / "phase_gates.yaml"
V2_GATES_PATH = ROOT / "configs" / "app_layer" / "phase_gates_v2.yaml"


def _normalize_phase(phase: str) -> str:
    stripped = phase.lstrip("0")
    return stripped or "0"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _load_phase_gates(phase: str, gates_path: Path) -> dict[str, Any]:
    gates_doc = _load_yaml(gates_path)
    phases = gates_doc.get("phases") or {}
    for key in (phase, phase.zfill(2), _normalize_phase(phase), _normalize_phase(phase).zfill(2)):
        entry = phases.get(str(key))
        if isinstance(entry, dict):
            return entry
    return {}


def _all_phase_keys(gates_path: Path) -> list[str]:
    gates_doc = _load_yaml(gates_path)
    phases = gates_doc.get("phases") or {}
    return sorted(phases.keys(), key=lambda k: int(_normalize_phase(str(k))))


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd or ROOT, env=env or os.environ.copy(), check=True)


def _validate_required_env(phase_cfg: dict[str, Any]) -> int:
    required_env = phase_cfg.get("required_env")
    if not isinstance(required_env, list):
        return 0
    missing = [str(name) for name in required_env if not os.environ.get(str(name))]
    if missing:
        for name in missing:
            print(f"error: required env var not set: {name}", file=sys.stderr)
        return 1
    return 0


def _validate_production_lock_v2(gates_path: Path) -> int:
    gates_doc = _load_yaml(gates_path)
    lock_raw = gates_doc.get("production_lock_v2")
    if not isinstance(lock_raw, dict):
        return 0
    from spark.core.app_profile import AppProfile
    from spark.core.config import Settings, settings
    from spark.core.production_lock import AppLayerV2ProductionLock, validate_app_layer_v2_lock_at_startup

    lock = AppLayerV2ProductionLock(
        require_dual_admission=bool(lock_raw.get("require_dual_admission", True)),
        require_ticket_freshness_check=bool(lock_raw.get("require_ticket_freshness_check", True)),
        require_sse_connection_governor=bool(lock_raw.get("require_sse_connection_governor", True)),
        require_atomic_redis_pop=bool(lock_raw.get("require_atomic_redis_pop", True)),
        require_stream_completion_contract=bool(
            lock_raw.get("require_stream_completion_contract", True)
        ),
        min_sse_pool_size=int(lock_raw.get("min_sse_pool_size", 8)),
        max_sse_per_user=int(lock_raw.get("max_sse_per_user", 5)),
        forbid_system_principal_outside_test=bool(
            lock_raw.get("forbid_system_principal_outside_test", True)
        ),
        require_audit_export_hmac=bool(lock_raw.get("require_audit_export_hmac", True)),
    )
    prev_lock = os.environ.get("APP_LAYER_V2_LOCK")
    prev_pool = settings.db_stream_pool_size
    original_app_profile = Settings.app_profile
    production_profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        redis_required=True,
        global_rate_limit_rpm=0,
        require_ticket_freshness_check=True,
        sse_max_connections_per_user=int(lock_raw.get("max_sse_per_user", 5)),
    )
    os.environ["APP_LAYER_V2_LOCK"] = "1"
    try:
        settings.db_stream_pool_size = max(prev_pool, lock.min_sse_pool_size)
        Settings.app_profile = property(lambda self: production_profile)
        validate_app_layer_v2_lock_at_startup(lock, spark_profile="production")
    except RuntimeError as exc:
        print(f"error: production_lock_v2 validation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        Settings.app_profile = original_app_profile
        settings.db_stream_pool_size = prev_pool
        if prev_lock is None:
            os.environ.pop("APP_LAYER_V2_LOCK", None)
        else:
            os.environ["APP_LAYER_V2_LOCK"] = prev_lock
    return 0


def _run_phase(
    phase: str,
    *,
    gates_path: Path,
    skip_web: bool,
    pytest_paths: list[str] | None,
) -> int:
    phase_cfg = _load_phase_gates(phase, gates_path)
    if not phase_cfg and phase not in {"0", "00"}:
        print(f"warning: no entry for phase {phase} in {gates_path}", file=sys.stderr)

    rc = _validate_required_env(phase_cfg)
    if rc != 0:
        return rc

    if phase in {"12", "012"} and gates_path.name == "phase_gates_v2.yaml":
        rc = _validate_production_lock_v2(gates_path)
        if rc != 0:
            return rc

    paths: list[str] = list(pytest_paths or [])
    cfg_pytest = phase_cfg.get("pytest")
    if isinstance(cfg_pytest, list):
        paths.extend(str(p) for p in cfg_pytest)

    if paths:
        existing = [p for p in paths if (ROOT / p).exists()]
        missing = [p for p in paths if not (ROOT / p).exists()]
        for path in missing:
            print(f"warning: pytest path not found (skipped): {path}", file=sys.stderr)
        if existing:
            _run(["uv", "run", "pytest", *existing, "-q", "--tb=short"])
        elif phase in {"0", "00"}:
            print("phase 0: some pytest paths not found yet — ok for scaffold")
        else:
            print(f"error: no pytest files found for phase {phase}", file=sys.stderr)
            return 1

    scripts = phase_cfg.get("scripts")
    if isinstance(scripts, list):
        for script in scripts:
            script_path = ROOT / str(script)
            if not script_path.is_file():
                print(f"error: script not found: {script_path}", file=sys.stderr)
                return 1
            env = os.environ.copy()
            if script_path.name == "banned_patterns_v2.sh":
                env["APP_LAYER_V2_BANNED_STRICT"] = "1"
            _run([str(script_path)], env=env)

    if skip_web:
        return 0

    web_steps = phase_cfg.get("web")
    if isinstance(web_steps, list):
        web_dir = ROOT / "web"
        for step in web_steps:
            parts = str(step).split()
            _run(parts, cwd=web_dir)

    e2e_specs = phase_cfg.get("e2e")
    if isinstance(e2e_specs, list):
        web_dir = ROOT / "web"
        for spec in e2e_specs:
            _run(["npm", "run", "test:e2e", "--", str(spec)], cwd=web_dir)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run app-layer remediation phase gates")
    parser.add_argument(
        "--phase",
        required=True,
        help="Phase number (0–13) or 'all'",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Phase gates YAML (default: phase_gates.yaml; use phase_gates_v2.yaml for v2)",
    )
    parser.add_argument(
        "--pytest",
        action="append",
        dest="pytest_paths",
        default=None,
        help="Additional pytest path(s)",
    )
    parser.add_argument(
        "--skip-web",
        action="store_true",
        help="Skip web npm test / tsc / e2e steps",
    )
    args = parser.parse_args(argv)

    if args.manifest:
        gates_path = Path(args.manifest)
        if not gates_path.is_absolute():
            gates_path = ROOT / gates_path
    else:
        gates_path = DEFAULT_GATES_PATH

    if not gates_path.is_file():
        print(f"error: manifest not found: {gates_path}", file=sys.stderr)
        return 1

    if args.phase.lower() == "all":
        for key in _all_phase_keys(gates_path):
            print(f"=== phase {key} ===", flush=True)
            rc = _run_phase(
                str(key),
                gates_path=gates_path,
                skip_web=args.skip_web,
                pytest_paths=args.pytest_paths,
            )
            if rc != 0:
                return rc
        print(f"app_layer phase gate all ({gates_path.name}): OK")
        return 0

    rc = _run_phase(
        args.phase,
        gates_path=gates_path,
        skip_web=args.skip_web,
        pytest_paths=args.pytest_paths,
    )
    if rc != 0:
        return rc

    print(f"app_layer phase gate {args.phase} ({gates_path.name}): OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
