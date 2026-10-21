"""Application-layer production profile (app-layer remediation Phase 0 + v2).

Encodes non-negotiable defaults for API gateway, auth, streaming, and Redis
requirements. RAG spine behavior remains in ``production_profile`` / settings.

v2 fields (``remediation_blueprint_app_layerv2/``) are scaffolded in Phase 0;
enforcement lands in Phases 1–12.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppProfile:
    """Hardened defaults for the API + presentation layer."""

    auth_required: bool = True
    fail_closed_on_missing_auth: bool = True
    allow_system_principal_fallback: bool = False
    redis_required: bool = True
    live_token_stream_default: bool = True
    global_rate_limit_rpm: int = 600
    login_max_attempts_per_ip: int = 20
    login_max_failures: int = 5
    login_failure_window_sec: int = 900
    login_lockout_sec: int = 900
    stream_ticket_ttl_sec: int = 120
    # --- v2 admission / stream security (enforced Phases 1–12) ---
    sse_max_connections_per_user: int = 5
    transactional_max_inflight_per_worker: int = 200
    sse_max_inflight_per_worker: int = 500
    require_ticket_freshness_check: bool = True
    stream_tokens_provisional_only: bool = True
    provisional_tokens_required: bool = True
    require_ticket_for_sse: bool = True

    @classmethod
    def for_env(cls, *, app_env: str, spark_profile: str) -> AppProfile:
        """Resolve profile from runtime environment."""
        profile = (spark_profile or "dev").strip().lower()
        env = (app_env or "development").strip().lower()

        if profile == "test":
            return cls(
                auth_required=False,
                fail_closed_on_missing_auth=False,
                allow_system_principal_fallback=False,
                redis_required=False,
                live_token_stream_default=False,
                global_rate_limit_rpm=0,
                login_max_attempts_per_ip=0,
                login_max_failures=5,
                require_ticket_freshness_check=False,
                require_ticket_for_sse=False,
            )

        if env == "production":
            return cls(
                auth_required=True,
                fail_closed_on_missing_auth=True,
                allow_system_principal_fallback=False,
                redis_required=True,
                live_token_stream_default=True,
            )

        # dev / staging — hardened auth, relaxed Redis for local laptops
        return cls(
            auth_required=True,
            fail_closed_on_missing_auth=False,
            allow_system_principal_fallback=True,
            redis_required=False,
            live_token_stream_default=False,
            require_ticket_for_sse=False,
        )

    def validate_for_production(self, *, app_env: str, spark_profile: str) -> None:
        """Fail fast when production is misconfigured for the app layer."""
        if app_env.strip().lower() != "production":
            return
        if spark_profile.strip().lower() == "test":
            raise RuntimeError(
                "SPARK_PROFILE=test is not allowed when APP_ENV=production"
            )
        if not self.fail_closed_on_missing_auth:
            raise RuntimeError(
                "AppProfile.fail_closed_on_missing_auth must be True when APP_ENV=production"
            )
        if self.allow_system_principal_fallback:
            raise RuntimeError(
                "AppProfile.allow_system_principal_fallback must be False when APP_ENV=production"
            )
        if not self.redis_required:
            raise RuntimeError(
                "AppProfile.redis_required must be True when APP_ENV=production"
            )
