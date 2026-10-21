#!/usr/bin/env python3
"""Pilot RAG soak report-shape check (Phase 15) — dry-run ONLY.

This script never drove real load: its non-dry-run path slept random sub-second
delays and published them as P95 "latency", which is worse than no data. That
path now refuses. For real numbers, run scripts/profile_rag_hotpath.py inside
the spark_api container (in-process, no auth required).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# parents[2]: this file lives at scripts/load/, the repo root is two levels up
# (parents[1] pointed the default profile at scripts/configs/... — never valid).
ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "configs" / "load" / "pilot_profile.yaml"


def _load_profile(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


async def run_soak(*, profile: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    rag_cfg = profile.get("rag") or {}
    concurrent = int(rag_cfg.get("concurrent_queries") or 100)
    slo_p95 = float(rag_cfg.get("slo_p95_seconds") or 8.0)
    max_false_trip = float(rag_cfg.get("max_circuit_false_trip_pct") or 0.0)

    if dry_run:
        latencies = [slo_p95 * 0.6 for _ in range(concurrent)]
        false_trip_pct = 0.0
    else:
        # The old non-dry-run path did asyncio.sleep(random.uniform(...)) and
        # published the result as a P95 "measurement" — numbers that look real
        # but measure nothing. Refuse rather than mislead: real per-stage
        # latency comes from scripts/profile_rag_hotpath.py run in-process
        # inside the api container.
        raise NotImplementedError(
            "soak_rag has no real load driver (it only simulated latencies). "
            "Use --dry-run for report-shape checks, or run "
            "scripts/profile_rag_hotpath.py inside the spark_api container "
            "for real measurements."
        )

    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    passed = p95 <= slo_p95 and false_trip_pct <= max_false_trip
    return {
        "suite": "rag_soak",
        "started_at": datetime.now(tz=UTC).isoformat(),
        "concurrent_queries": concurrent,
        "samples": len(latencies),
        "p95_seconds": round(p95, 3),
        "slo_p95_seconds": slo_p95,
        "circuit_false_trip_pct": round(false_trip_pct, 3),
        "max_circuit_false_trip_pct": max_false_trip,
        "passed": passed,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG load soak")
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    profile = _load_profile(args.profile)
    report = asyncio.run(run_soak(profile=profile, dry_run=args.dry_run))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
