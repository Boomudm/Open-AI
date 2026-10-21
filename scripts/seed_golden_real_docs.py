#!/usr/bin/env python3
"""Ingest the 5 real client documents used by the ``golden_real_docs`` eval suite.

These documents (KUKA/Oriental vendor manuals + a client's PLC I/O mapping and
wiring diagrams) are copyrighted and are NOT committed to this repo — they
must be supplied out-of-band (secure fixture storage / CI secret) and pointed
to via ``GOLDEN_REAL_DOCS_DIR``. This script builds an ingest manifest for
them and reuses ``ingest_batch_cli``'s manifest-driven enqueue path (the same
validation/enqueue code as ``POST /ingest/file``), then waits for the Celery
ingestion jobs to drain before returning.

Usage:
    GOLDEN_REAL_DOCS_DIR=/secure/fixtures/golden_real_docs \\
        uv run python scripts/seed_golden_real_docs.py

See configs/eval/golden_real_docs.yaml for the eval cases these documents
back, and docs/internal/ for the expected filenames.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

# filename -> (doc_type, machine_id or None)
# machine_id column is varchar(20) — keep IDs within that.
_EXPECTED_FILES: dict[str, tuple[str, str | None]] = {
    "KSS_Manual.pdf": ("machine_manual", "MC-GOLDEN-KSS"),
    "Oriental_Servo_Manual.pdf": ("machine_manual", "MC-GOLDEN-SERVO"),
    "MAPPING.xlsx": ("io_mapping", None),
    "mapping_diagram.pdf": ("io_mapping", None),
    "wiring_diagram.pdf": ("drawing", None),
}


def _build_manifest(docs_dir: Path, factory_id: str) -> list[dict]:
    missing = [name for name in _EXPECTED_FILES if not (docs_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing expected golden real docs in {docs_dir}: {missing}"
        )
    manifest: list[dict] = []
    for name, (doc_type, machine_id) in _EXPECTED_FILES.items():
        item: dict = {
            "path": str(docs_dir / name),
            "factory_id": factory_id,
            "doc_type": doc_type,
        }
        if machine_id:
            item["machine_id"] = machine_id
        manifest.append(item)
    return manifest


def _seed(docs_dir: Path, *, factory_id: str, wait_timeout: int) -> int:
    import yaml

    manifest_items = _build_manifest(docs_dir, factory_id)
    manifest_path = docs_dir / "_golden_real_docs_manifest.generated.yaml"
    manifest_path.write_text(
        yaml.safe_dump({"files": manifest_items}, allow_unicode=True), encoding="utf-8"
    )

    # Shell out to the existing CLIs rather than importing them — they're
    # designed as standalone entrypoints (each does its own sys.path setup),
    # and this keeps this script from depending on scripts/ being importable.
    ingest = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_batch_cli.py"), "--manifest", str(manifest_path)],
        cwd=ROOT,
    )
    if ingest.returncode != 0:
        return ingest.returncode

    wait = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "wait_ingest_idle.py"),
            "--timeout",
            str(wait_timeout),
            "--poll",
            "5",
        ],
        cwd=ROOT,
    )
    return wait.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(os.environ.get("GOLDEN_REAL_DOCS_DIR", "")),
        help="Directory containing the 5 real documents (env: GOLDEN_REAL_DOCS_DIR)",
    )
    parser.add_argument(
        "--factory-id",
        default=os.environ.get("GOLDEN_REAL_DOCS_FACTORY_ID", "F-GOLDEN"),
        help="Factory scope to ingest under (must already exist — see scripts/seed_demo.py)",
    )
    parser.add_argument("--wait-timeout", type=int, default=1800, help="Max seconds to wait for ingestion to drain")
    args = parser.parse_args(argv)

    if not args.docs_dir or not args.docs_dir.is_dir():
        print(
            "GOLDEN_REAL_DOCS_DIR is not set or not a directory — the 5 real "
            "documents are gitignored and must be supplied out-of-band "
            "(see module docstring).",
            file=sys.stderr,
        )
        return 2

    return _seed(args.docs_dir, factory_id=args.factory_id, wait_timeout=args.wait_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
