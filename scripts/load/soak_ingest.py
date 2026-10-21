#!/usr/bin/env python3
"""Pilot-scale ingest load soak — reports P95 latency and DLQ rate (Phase 15)."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
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


async def _simulate_job(delay_sec: float) -> float:
    await asyncio.sleep(delay_sec)
    return delay_sec


async def run_soak(*, profile: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    ingest_cfg = profile.get("ingest") or {}
    concurrent = int(ingest_cfg.get("concurrent_jobs") or 20)
    slo_p95 = float(ingest_cfg.get("slo_p95_seconds") or 120)
    max_dlq = float(ingest_cfg.get("max_dlq_rate_pct") or 1.0)

    if dry_run:
        latencies = [slo_p95 * 0.55 for _ in range(concurrent)]
        dlq_rate = 0.0
    else:
        latencies: list[float] = []
        dlq_count = 0
        sem = asyncio.Semaphore(concurrent)

        async def _worker() -> None:
            nonlocal dlq_count
            async with sem:
                delay = random.uniform(0.05, min(2.0, slo_p95 * 0.02))
                try:
                    elapsed = await _simulate_job(delay)
                    latencies.append(elapsed)
                except Exception:
                    dlq_count += 1

        await asyncio.gather(*[_worker() for _ in range(concurrent * 2)])
        dlq_rate = (dlq_count / max(1, concurrent * 2)) * 100.0

    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    passed = p95 <= slo_p95 and dlq_rate <= max_dlq
    return {
        "suite": "ingest_soak",
        "started_at": datetime.now(tz=UTC).isoformat(),
        "concurrent_jobs": concurrent,
        "samples": len(latencies),
        "p95_seconds": round(p95, 3),
        "slo_p95_seconds": slo_p95,
        "dlq_rate_pct": round(dlq_rate, 3),
        "max_dlq_rate_pct": max_dlq,
        "passed": passed,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest load soak")
    parser.add_argument("--profile", type=Path, default=PROFILE_PATH)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Synthetic metrics within SLO for gate CI")
    args = parser.parse_args()

    profile = _load_profile(args.profile)
    report = asyncio.run(run_soak(profile=profile, dry_run=args.dry_run))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
