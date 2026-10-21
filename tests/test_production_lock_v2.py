"""Production lock v2 manifest validation (remediation blueprint v2 Phase 0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark.contracts.degradation_contract import (
    circuit_open_degradation,
    healthy_degradation,
    policy_block_degradation,
)
from spark.core.production_lock import (
    load_production_lock_manifest,
    validate_production_lock_at_startup,
)


def test_production_lock_v3_manifest_loads() -> None:
    manifest = load_production_lock_manifest()
    assert manifest.version == 3
    assert manifest.required["ingest_policy_enabled"] is True
    assert manifest.required["unknown_ingest_error"] == "permanent"
    assert manifest.required.get("require_gpu_rerank") is True
    assert manifest.required.get("degraded_rerank_policy") == "rank_gate"
    assert "SPARK_SEED_SKIP_EMBED" in manifest.forbidden_env
    assert "SPARK_STREAM_LIVE_TOKENS" in manifest.forbidden_env


def test_production_lock_v3_manifest_path_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "configs" / "production_lock_v3.yaml").is_file()


def test_validate_production_lock_skips_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_PROFILE", "test")
    manifest = validate_production_lock_at_startup(spark_profile="test")
    assert manifest.version == 3


def test_validate_production_lock_rejects_forbidden_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_PROFILE", "dev")
    monkeypatch.setenv("RAG_DISABLE_SAFETY", "1")
    with pytest.raises(RuntimeError, match="RAG_DISABLE_SAFETY"):
        validate_production_lock_at_startup(spark_profile="dev")


def test_degradation_contract_serializable() -> None:
    for factory in (healthy_degradation, policy_block_degradation, circuit_open_degradation):
        payload = factory().to_dict()
        assert "vector_available" in payload
        assert "user_message_key" in payload
        assert "system_status" in payload


def test_degradation_policy_block_is_fail_closed() -> None:
    assert policy_block_degradation().fail_closed is True


def test_production_lock_validates_dev_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_PROFILE", "dev")
    monkeypatch.delenv("RAG_DISABLE_SAFETY", raising=False)
    monkeypatch.delenv("SPARK_SEED_SKIP_EMBED", raising=False)
    validate_production_lock_at_startup(spark_profile="dev")
