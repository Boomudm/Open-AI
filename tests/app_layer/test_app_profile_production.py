"""App-layer AppProfile production invariants (Phase 0)."""

from __future__ import annotations

import pytest

from spark.core.app_profile import AppProfile


def test_production_profile_fail_closed() -> None:
    profile = AppProfile.for_env(app_env="production", spark_profile="production")
    assert profile.auth_required is True
    assert profile.fail_closed_on_missing_auth is True
    assert profile.allow_system_principal_fallback is False
    assert profile.redis_required is True
    assert profile.live_token_stream_default is True
    assert profile.global_rate_limit_rpm > 0


def test_test_profile_allows_relaxed_gates_for_ci() -> None:
    profile = AppProfile.for_env(app_env="development", spark_profile="test")
    assert profile.allow_system_principal_fallback is False
    assert profile.redis_required is False
    assert profile.global_rate_limit_rpm == 0
    assert profile.login_max_attempts_per_ip == 0


def test_production_validate_rejects_demo_fallback_flags() -> None:
    bad = AppProfile(
        fail_closed_on_missing_auth=False,
        allow_system_principal_fallback=True,
    )
    with pytest.raises(RuntimeError, match="fail_closed_on_missing_auth"):
        bad.validate_for_production(app_env="production", spark_profile="production")


def test_settings_app_profile_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SPARK_PROFILE", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    cfg = Settings()
    assert cfg.app_profile.fail_closed_on_missing_auth is True
    cfg.validate_app_profile()
