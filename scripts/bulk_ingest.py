#!/usr/bin/env python3
"""Bulk ingest via POST /api/v1/ingest/batch (manifest JSON)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk ingest documents via Neo Chat API")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument("--manifest", required=True, help="JSON manifest path")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    headers = {"Authorization": f"Bearer {args.token}"}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{args.api.rstrip('/')}/api/v1/ingest/batch",
            headers=headers,
            json=manifest,
        )
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
