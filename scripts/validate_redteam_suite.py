#!/usr/bin/env python3
"""Validate red-team / adversarial eval suite size (Phase 15)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "eval" / "adversarial.yaml"


def _load_cases(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    include = raw.get("include")
    if include:
        include_path = Path(str(include))
        if not include_path.is_absolute():
            include_path = ROOT / "configs" / include
        return _load_cases(include_path)
    cases = list(raw.get("cases") or [])
    configs_root = ROOT / "configs"
    for item in raw.get("includes") or []:
        rel = Path(str(item))
        inc_path = configs_root / rel
        if not inc_path.is_file():
            inc_path = path.parent / rel
        inc_raw = yaml.safe_load(inc_path.read_text(encoding="utf-8")) or {}
        cases.extend(list(inc_raw.get("cases") or []))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate adversarial/red-team case count")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--min-cases", type=int, default=50)
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"FAIL: missing {args.config}", file=sys.stderr)
        return 1

    cases = _load_cases(args.config)
    categories = {str(c.get("category") or "unknown") for c in cases if isinstance(c, dict)}
    if len(cases) < args.min_cases:
        print(
            f"FAIL: adversarial suite has {len(cases)} cases, need >= {args.min_cases}",
            file=sys.stderr,
        )
        return 1

    required = {"injection_manual", "wrong_machine", "numeric_trap", "ocr_hidden", "ocr_garbage"}
    missing = required - categories - {"ocr_garbage"}  # ocr_garbage satisfies ocr_hidden
    if "ocr_garbage" in categories:
        missing -= {"ocr_hidden"}
    if missing:
        print(f"FAIL: missing red-team categories: {sorted(missing)}", file=sys.stderr)
        return 1

    print(f"OK red-team suite: {len(cases)} cases, categories={len(categories)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
