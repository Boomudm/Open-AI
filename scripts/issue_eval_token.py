#!/usr/bin/env python3
"""Issue HMAC-signed eval pass token after production_lock_v3 report validation (Phase 13)."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def _main_async(args: argparse.Namespace) -> int:
    from spark.ingestion.eval_gate import current_breaking_snapshot, store_eval_token
    from spark.ingestion.eval_token import hash_report_dir, sign_eval_payload

    validate_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "validate_production_lock_v3.py"),
        "--lock",
        str(args.lock),
        "--report-dir",
        str(args.report_dir),
        "--strict",
    ]
    proc = subprocess.run(validate_cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        return proc.returncode

    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    required_suites = [str(name) for name in (lock.get("required_suites") or [])]
    report_sha256 = hash_report_dir(args.report_dir, suite_names=required_suites)
    snapshot = current_breaking_snapshot()
    config_hash = snapshot.config_hash()
    expires_at = (datetime.now(tz=UTC) + timedelta(seconds=args.ttl_sec)).isoformat()
    payload = {
        "report_sha256": report_sha256,
        "lock_version": int(lock.get("version") or 3),
        "config_hash": config_hash,
        "factory_id": args.factory_id or "global",
        "issued_by": args.issued_by,
        "expires_at": expires_at,
    }
    signed = sign_eval_payload(payload)
    await store_eval_token(
        factory_id=args.factory_id,
        config_hash=config_hash,
        signed_token=signed,
        ttl_sec=args.ttl_sec,
    )
    print(f"eval_token issued for factory={args.factory_id or 'global'}")
    print(f"config_hash={config_hash}")
    print(f"report_sha256={report_sha256}")
    print(f"lock_version={payload['lock_version']}")
    print(f"expires_at={expires_at}")
    print(f"signature={signed['signature'][:16]}...")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue signed ingest swap eval token after eval pass")
    parser.add_argument(
        "--report-dir",
        type=Path,
        required=True,
        help="Directory containing {suite}.json eval reports",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=ROOT / "configs" / "eval" / "production_lock_v3.json",
    )
    parser.add_argument("--factory-id", default=None, help="Factory scope (default: global)")
    parser.add_argument("--ttl-sec", type=int, default=86_400, help="Token TTL in seconds")
    parser.add_argument("--issued-by", default="operator", help="Actor label for audit")
    args = parser.parse_args()
    if not args.report_dir.is_dir():
        print(f"ERROR: report dir not found: {args.report_dir}", file=sys.stderr)
        return 1
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
