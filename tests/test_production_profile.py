"""ProductionProfile env defaults and factory override merge."""

from __future__ import annotations

import pytest

from spark.core.production_profile import ProductionProfile
from spark.services.factory_config_service import FactoryConfigService


def test_production_profile_hardened_defaults() -> None:
    profile = ProductionProfile.hardened_defaults()
    assert profile.ingest_policy_enabled is True
    assert profile.rag_circuit_enabled is True
    assert profile.lexical_engine == "postgres_thai_v3"
    assert profile.query_rewrite_enabled is True
    assert profile.extractive_first_for_safety_types is False
    assert profile.extractive_first_enabled is False
    assert profile.sparse_vectors_enabled is True


def test_production_profile_test_defaults_relaxed() -> None:
    profile = ProductionProfile.test_defaults()
    assert profile.ingest_policy_enabled is False
    assert profile.rag_circuit_enabled is False


def test_production_profile_from_settings_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    profile = ProductionProfile.from_settings()
    assert profile.ingest_policy_enabled is True
    assert profile.rag_circuit_enabled is True


def test_production_profile_from_settings_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "test")
    profile = ProductionProfile.from_settings()
    assert profile.ingest_policy_enabled is False
    assert profile.rag_circuit_enabled is False


def test_production_profile_factory_override_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    base_cfg: dict = {"features": {}}
    profile = ProductionProfile.for_factory(base_cfg)
    assert profile.rag_circuit_enabled is True

    overridden = ProductionProfile.for_factory(
        {
            "features": {
                "lexical_engine": "postgres_v2",
            }
        }
    )
    assert overridden.lexical_engine == "postgres_thai_v3"
    assert overridden.rag_circuit_enabled is True


def test_factory_cannot_disable_security_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    profile = ProductionProfile.for_factory(
        {"features": {"ingest_policy_enabled": False, "rag_circuit_enabled": False}}
    )
    assert profile.ingest_policy_enabled is True
    assert profile.rag_circuit_enabled is True


def test_factory_config_service_production_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    svc = FactoryConfigService()
    cfg = {
        "features": {
            "lexical_engine": "postgres_v2",
        }
    }
    profile = svc.production_profile(cfg)
    assert profile.lexical_engine == "postgres_thai_v3"
    assert profile.ingest_policy_enabled is True


def test_production_profile_legacy_remediation_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    profile = ProductionProfile.for_factory(
        {"remediation": {"lexical_engine": "postgres_v2", "query_rewrite_enabled": True}}
    )
    assert profile.query_rewrite_enabled is True
    assert profile.lexical_engine == "postgres_thai_v3"


def test_resolve_lexical_engine_for_retrieval_identity() -> None:
    from spark.core.production_profile import resolve_lexical_engine_for_retrieval

    assert resolve_lexical_engine_for_retrieval("postgres_thai_v3") == "postgres_thai_v3"


def test_factory_features_patch_rejects_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    from spark.schemas.factory_settings import FactoryFeaturesPatch

    with pytest.raises(ValidationError):
        FactoryFeaturesPatch(ingest_policy_enabled=False)
