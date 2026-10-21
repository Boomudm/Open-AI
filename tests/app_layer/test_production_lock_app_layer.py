"""Phase 12 — production lock app_layer gates."""

from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.production_lock import (
    AppLayerProductionLock,
    AppLayerV2ProductionLock,
    load_production_lock_manifest,
    validate_app_layer_lock_at_startup,
    validate_app_layer_v2_lock_at_startup,
)


def test_manifest_includes_app_layer_section() -> None:
    manifest = load_production_lock_manifest()
    assert manifest.app_layer is not None
    assert manifest.app_layer.require_redis is True
    assert manifest.app_layer.require_fail_closed_auth is True
    assert manifest.app_layer.min_api_workers >= 2


def test_validate_app_layer_rejects_low_worker_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.core.app_profile import AppProfile

    profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        redis_required=True,
        global_rate_limit_rpm=0,
    )
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(type(settings), "app_profile", property(lambda self: profile))
    monkeypatch.setenv("ONPREM_API_WORKERS", "1")
    cfg = AppLayerProductionLock(min_api_workers=2)
    with pytest.raises(RuntimeError, match="ONPREM_API_WORKERS"):
        validate_app_layer_lock_at_startup(cfg, spark_profile="production")


def test_validate_app_layer_skips_test_profile() -> None:
    cfg = AppLayerProductionLock(min_api_workers=4)
    validate_app_layer_lock_at_startup(cfg, spark_profile="test")


def test_manifest_includes_app_layer_v2_section() -> None:
    manifest = load_production_lock_manifest()
    assert manifest.app_layer_v2 is not None
    assert manifest.app_layer_v2.require_dual_admission is True
    assert manifest.app_layer_v2.min_sse_pool_size >= 8
    assert manifest.app_layer_v2.require_audit_export_hmac is True


def _v2_ready_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.app_profile import AppProfile

    profile = AppProfile(
        auth_required=True,
        fail_closed_on_missing_auth=True,
        allow_system_principal_fallback=False,
        redis_required=True,
        global_rate_limit_rpm=0,
        require_ticket_freshness_check=True,
        sse_max_connections_per_user=5,
    )
    monkeypatch.setattr(type(settings), "app_profile", property(lambda self: profile))


def test_validate_app_layer_v2_requires_hmac_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppLayerV2ProductionLock(require_audit_export_hmac=True)
    _v2_ready_profile(monkeypatch)
    monkeypatch.delenv("AUDIT_EXPORT_HMAC_SECRET", raising=False)
    monkeypatch.setenv("APP_LAYER_V2_LOCK", "1")
    with pytest.raises(RuntimeError, match="AUDIT_EXPORT_HMAC_SECRET"):
        validate_app_layer_v2_lock_at_startup(cfg, spark_profile="production")


def test_validate_app_layer_v2_passes_with_hmac_and_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppLayerV2ProductionLock(
        require_audit_export_hmac=True,
        min_sse_pool_size=8,
        require_stream_completion_contract=False,
    )
    _v2_ready_profile(monkeypatch)
    monkeypatch.setenv("AUDIT_EXPORT_HMAC_SECRET", "test-hmac-secret")
    monkeypatch.setenv("APP_LAYER_V2_LOCK", "1")
    monkeypatch.setattr(settings, "db_stream_pool_size", 10)
    validate_app_layer_v2_lock_at_startup(cfg, spark_profile="production")


def test_validate_app_layer_v2_rejects_low_sse_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppLayerV2ProductionLock(min_sse_pool_size=8)
    _v2_ready_profile(monkeypatch)
    monkeypatch.setenv("APP_LAYER_V2_LOCK", "1")
    monkeypatch.setenv("AUDIT_EXPORT_HMAC_SECRET", "test-hmac-secret")
    monkeypatch.setattr(settings, "db_stream_pool_size", 4)
    with pytest.raises(RuntimeError, match="db_stream_pool_size"):
        validate_app_layer_v2_lock_at_startup(cfg, spark_profile="production")
