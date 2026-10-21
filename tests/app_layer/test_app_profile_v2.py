"""App-layer v2 AppProfile scaffold fields (Phase 0)."""

from __future__ import annotations

from spark.core.app_profile import AppProfile


def test_v2_fields_present_on_production_profile() -> None:
    profile = AppProfile.for_env(app_env="production", spark_profile="production")
    assert profile.sse_max_connections_per_user == 5
    assert profile.transactional_max_inflight_per_worker == 200
    assert profile.sse_max_inflight_per_worker == 500
    assert profile.require_ticket_freshness_check is True
    assert profile.stream_tokens_provisional_only is True
    assert profile.provisional_tokens_required is True
    assert profile.require_ticket_for_sse is True


def test_v2_fields_relaxed_in_test_profile() -> None:
    profile = AppProfile.for_env(app_env="development", spark_profile="test")
    assert profile.require_ticket_freshness_check is False
    assert profile.require_ticket_for_sse is False
