"""SPARK_PROFILE startup guards."""

from __future__ import annotations

import pytest

from spark.core.config import Settings


def test_seed_skip_embed_forbidden_outside_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_SEED_SKIP_EMBED", "1")
    monkeypatch.delenv("SPARK_TESTING", raising=False)
    settings = Settings(spark_profile="production", allow_dummy_embeddings=False, spark_testing=False)
    with pytest.raises(RuntimeError, match="SPARK_SEED_SKIP_EMBED"):
        settings.validate_profile_env()


def test_seed_skip_embed_allowed_in_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_SEED_SKIP_EMBED", "1")
    settings = Settings(spark_profile="test")
    settings.validate_profile_env()


def test_low_llm_timeout_forbidden_outside_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_LLM_TIMEOUT_SEC", "0.1")
    settings = Settings(spark_profile="dev")
    with pytest.raises(RuntimeError, match="RAG_LLM_TIMEOUT_SEC"):
        settings.validate_profile_env()


def test_embedder_assert_respects_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings as live_settings
    from spark.ingestion.embedder import assert_dummy_embeddings_allowed

    monkeypatch.setenv("SPARK_SEED_SKIP_EMBED", "1")
    monkeypatch.delenv("SPARK_TESTING", raising=False)
    monkeypatch.setattr(live_settings, "spark_profile", "test")
    monkeypatch.setattr(live_settings, "allow_dummy_embeddings", False)
    monkeypatch.setattr(live_settings, "spark_testing", False)
    assert_dummy_embeddings_allowed()

    monkeypatch.setattr(live_settings, "spark_profile", "production")
    with pytest.raises(RuntimeError, match="SPARK_SEED_SKIP_EMBED"):
        assert_dummy_embeddings_allowed()

    monkeypatch.delenv("SPARK_SEED_SKIP_EMBED", raising=False)
