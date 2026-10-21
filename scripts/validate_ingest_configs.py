#!/usr/bin/env python3
"""Validate all ingest YAML configs resolve with merged profiles."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spark.ingestion.config_loader import list_document_types
from spark.ingestion.config_resolver import ConfigError, resolve_ingest_config
from spark.ingestion.config_schema import validate_all_ingestion_configs


def main() -> int:
    try:
        validate_all_ingestion_configs()
    except Exception as exc:
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    doc_types = list_document_types()
    if not doc_types:
        print("No ingestion configs found.", file=sys.stderr)
        return 1

    errors: list[str] = []
    for document_type in doc_types:
        try:
            resolved = resolve_ingest_config(document_type, {})
        except (ConfigError, FileNotFoundError, ValueError) as exc:
            errors.append(f"{document_type}: {exc}")
            continue
        chunk = resolved.chunking
        embed = resolved.embedding
        print(
            f"{document_type}: parser={resolved.parser} "
            f"chunk_profile={chunk.profile} size={chunk.chunk_size} overlap={chunk.chunk_overlap} "
            f"embed_profile={embed.profile} dim={embed.expected_dim}"
        )

    if errors:
        print("\nValidation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"\nOK — {len(doc_types)} document types validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
