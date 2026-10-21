"""Batch ingest HTTP endpoints removed in Phase 2 — use scripts/ingest_batch_cli.py."""

from __future__ import annotations

from pathlib import Path

from spark.api.v1.endpoints import ingest as ingest_mod


def test_batch_http_routes_removed() -> None:
    route_paths = [getattr(r, "path", "") for r in ingest_mod.router.routes]
    assert "/ingest/batch" not in route_paths
    assert not any("/batch/" in p for p in route_paths)


def test_ingest_batch_cli_exists() -> None:
    cli_path = Path(__file__).resolve().parents[1] / "scripts" / "ingest_batch_cli.py"
    assert cli_path.is_file()
    source = cli_path.read_text(encoding="utf-8")
    assert "--manifest" in source
    assert "validate_upload_mime" in source
