"""Contract: Phase 13 legacy teardown — native-only spine."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase13_migration_guide_exists() -> None:
    path = ROOT / "docs" / "migrations" / "v0.6-native-only.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "INGEST_BACKEND=native" in text


def test_phase13_audit_script_exists() -> None:
    script = ROOT / "scripts" / "audit_dead_code.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111


def test_phase13_no_ragflow_settings_on_config() -> None:
    from spark.core.config import Settings

    fields = set(Settings.model_fields)
    assert "ragflow_api_url" not in fields
    assert "ragflow_api_key" not in fields
    assert "ragflow_dataset_id" not in fields


def test_phase13_deprecated_config_metric() -> None:
    from spark.core.metrics import deprecated_config_usage_total

    assert "deprecated_config_usage" in deprecated_config_usage_total._name


def test_phase13_legacy_synthesis_removed_from_facade() -> None:
    import spark.services.rag_service as facade

    assert not hasattr(facade, "_synthesize_from_docs")
    assert not hasattr(facade, "_format_manual_thai_steps")


def test_phase13_ingest_backend_resolver_removed() -> None:
    assert not (ROOT / "src" / "spark" / "services" / "ingest_backend_resolver.py").exists()


def test_phase13_src_ragflow_allowlist_only() -> None:
    allow = {
        "src/spark/core/deprecated_config.py",
    }
    hits: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in allow:
            continue
        if "ragflow" in path.read_text(encoding="utf-8").lower():
            hits.append(rel)
    assert hits == []
