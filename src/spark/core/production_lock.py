"""Production lock v3 — manifest validation for remediation blueprint v3 (Phase 13)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from spark.core.logging import get_logger

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_V3_PATH = _PROJECT_ROOT / "configs" / "production_lock_v3.yaml"
_MANIFEST_V2_PATH = _PROJECT_ROOT / "configs" / "production_lock_v2.yaml"

_BOOL_KEYS = frozenset(
    {
        "ingest_policy_enabled",
        "rag_circuit_enabled",
        "query_rewrite_enabled",
        "extractive_first_for_safety_types",
        "extractive_first_for_procedure",
        "sparse_vectors_enabled",
        "ml_classifier_enabled",
    }
)


@dataclass(frozen=True)
class AppLayerProductionLock:
    require_redis: bool = True
    require_fail_closed_auth: bool = True
    require_trust_ui_mapping: bool = True
    min_api_workers: int = 2


@dataclass(frozen=True)
class AppLayerV2ProductionLock:
    require_dual_admission: bool = True
    require_ticket_freshness_check: bool = True
    require_sse_connection_governor: bool = True
    require_atomic_redis_pop: bool = True
    require_stream_completion_contract: bool = True
    min_sse_pool_size: int = 8
    max_sse_per_user: int = 5
    forbid_system_principal_outside_test: bool = True
    require_audit_export_hmac: bool = True


@dataclass(frozen=True)
class ProductionLockManifest:
    version: int
    required: dict[str, Any]
    enforcement: dict[str, bool]
    forbidden_env: tuple[str, ...]
    app_layer: AppLayerProductionLock | None = None
    app_layer_v2: AppLayerV2ProductionLock | None = None

    @property
    def mandatory_factory_id_required(self) -> bool:
        return bool(self.required.get("mandatory_factory_id"))

    @property
    def mandatory_factory_id_enforced(self) -> bool:
        return bool(self.enforcement.get("mandatory_factory_id"))

    @property
    def sparse_encoder_id(self) -> str:
        return str(self.required.get("sparse_encoder") or "")


def load_production_lock_manifest(path: Path | None = None) -> ProductionLockManifest:
    if path is not None:
        manifest_path = path
    elif _MANIFEST_V3_PATH.is_file():
        manifest_path = _MANIFEST_V3_PATH
    else:
        manifest_path = _MANIFEST_V2_PATH
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Production lock manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path.name} must be a mapping")
    required = raw.get("required") or {}
    enforcement = raw.get("enforcement") or {}
    forbidden = raw.get("forbidden_env") or []
    if not isinstance(required, dict):
        raise ValueError(f"{manifest_path.name}.required must be a mapping")
    if not isinstance(enforcement, dict):
        raise ValueError(f"{manifest_path.name}.enforcement must be a mapping")
    if not isinstance(forbidden, list):
        raise ValueError(f"{manifest_path.name}.forbidden_env must be a list")
    app_layer_raw = raw.get("app_layer")
    app_layer: AppLayerProductionLock | None = None
    if isinstance(app_layer_raw, dict):
        app_layer = AppLayerProductionLock(
            require_redis=bool(app_layer_raw.get("require_redis", True)),
            require_fail_closed_auth=bool(
                app_layer_raw.get("require_fail_closed_auth", True)
            ),
            require_trust_ui_mapping=bool(
                app_layer_raw.get("require_trust_ui_mapping", True)
            ),
            min_api_workers=int(app_layer_raw.get("min_api_workers", 2)),
        )
    app_layer_v2_raw = raw.get("app_layer_v2")
    app_layer_v2: AppLayerV2ProductionLock | None = None
    if isinstance(app_layer_v2_raw, dict):
        app_layer_v2 = AppLayerV2ProductionLock(
            require_dual_admission=bool(app_layer_v2_raw.get("require_dual_admission", True)),
            require_ticket_freshness_check=bool(
                app_layer_v2_raw.get("require_ticket_freshness_check", True)
            ),
            require_sse_connection_governor=bool(
                app_layer_v2_raw.get("require_sse_connection_governor", True)
            ),
            require_atomic_redis_pop=bool(app_layer_v2_raw.get("require_atomic_redis_pop", True)),
            require_stream_completion_contract=bool(
                app_layer_v2_raw.get("require_stream_completion_contract", True)
            ),
            min_sse_pool_size=int(app_layer_v2_raw.get("min_sse_pool_size", 8)),
            max_sse_per_user=int(app_layer_v2_raw.get("max_sse_per_user", 5)),
            forbid_system_principal_outside_test=bool(
                app_layer_v2_raw.get("forbid_system_principal_outside_test", True)
            ),
            require_audit_export_hmac=bool(
                app_layer_v2_raw.get("require_audit_export_hmac", True)
            ),
        )
    return ProductionLockManifest(
        version=int(raw.get("version") or 2),
        required=required,
        enforcement={str(k): bool(v) for k, v in enforcement.items()},
        forbidden_env=tuple(str(item) for item in forbidden),
        app_layer=app_layer,
        app_layer_v2=app_layer_v2,
    )


def validate_production_lock_at_startup(*, spark_profile: str) -> ProductionLockManifest:
    """Validate manifest + profile alignment. No-op for SPARK_PROFILE=test."""
    profile = (spark_profile or "").strip().lower()
    manifest = load_production_lock_manifest()
    if profile == "test":
        return manifest

    for env_name in manifest.forbidden_env:
        if os.environ.get(env_name):
            raise RuntimeError(
                f"{env_name} is forbidden outside SPARK_PROFILE=test "
                f"(see configs/production_lock_v3.yaml)"
            )

    active = _profile_for_validation(profile)
    _validate_required_bools(manifest, active)
    _validate_lexical_engine(manifest, active)
    _validate_sparse_encoder(manifest, active)

    if manifest.required.get("unknown_ingest_error") != "permanent":
        raise RuntimeError(
            "production_lock_v2.required.unknown_ingest_error must be 'permanent'"
        )

    if not manifest.mandatory_factory_id_required:
        raise RuntimeError("production_lock_v2.required.mandatory_factory_id must be true")

    if manifest.mandatory_factory_id_required and not manifest.mandatory_factory_id_enforced:
        raise RuntimeError(
            "production_lock_v2.enforcement.mandatory_factory_id must be true when required"
        )

    if manifest.sparse_encoder_id and not manifest.enforcement.get("sparse_encoder"):
        log.info(
            "production_lock_sparse_encoder_deferred",
            sparse_encoder=manifest.sparse_encoder_id,
            detail="sparse_encoder enforcement disabled in manifest",
        )

    _validate_layout_parser(manifest, profile)
    _validate_require_gpu_rerank(manifest, profile)
    _validate_degraded_rerank_policy(manifest)
    validate_app_layer_lock_at_startup(
        manifest.app_layer,
        spark_profile=profile,
    )
    validate_app_layer_v2_lock_at_startup(
        manifest.app_layer_v2,
        spark_profile=profile,
    )

    log.info(
        "production_lock_validated",
        version=manifest.version,
        profile=profile,
        sparse_encoder=manifest.sparse_encoder_id,
        manifest=str(_MANIFEST_V3_PATH if _MANIFEST_V3_PATH.is_file() else _MANIFEST_V2_PATH),
    )
    return manifest


def _profile_for_validation(spark_profile: str) -> Any:
    """Resolve expected hardened profile for lock checks (not factory overrides)."""
    from spark.core.production_profile import ProductionProfile

    if spark_profile == "test":
        return ProductionProfile.test_defaults()
    return ProductionProfile.hardened_defaults()


def _validate_required_bools(manifest: ProductionLockManifest, active: Any) -> None:
    for key in _BOOL_KEYS:
        expected = manifest.required.get(key)
        if expected is None:
            continue
        if not isinstance(expected, bool):
            raise RuntimeError(f"production_lock_v2.required.{key} must be a boolean")
        actual = bool(getattr(active, key))
        if actual != expected:
            raise RuntimeError(
                f"production_lock_v2 mismatch for {key}: manifest={expected} profile={actual}"
            )


def _validate_lexical_engine(manifest: ProductionLockManifest, active: Any) -> None:
    expected = str(manifest.required.get("lexical_engine") or "").strip().lower()
    if not expected:
        return
    actual = str(getattr(active, "lexical_engine", "") or "").strip().lower()
    if actual != expected:
        raise RuntimeError(
            f"production_lock_v2 lexical_engine mismatch: manifest={expected} profile={actual}"
        )


def _validate_sparse_encoder(manifest: ProductionLockManifest, active: Any) -> None:
    expected = str(manifest.sparse_encoder_id or "").strip().lower()
    if not expected:
        return
    if not manifest.enforcement.get("sparse_encoder"):
        return
    actual = str(getattr(active, "sparse_encoder", "") or "").strip().lower()
    if actual != expected:
        raise RuntimeError(
            f"production_lock_v2 sparse_encoder mismatch: manifest={expected} profile={actual}"
        )


def _validate_layout_parser(manifest: ProductionLockManifest, spark_profile: str) -> None:
    from spark.core.config import settings

    expected = str(manifest.required.get("layout_parser") or "").strip().lower()
    if not expected:
        return
    if spark_profile == "test":
        return
    if spark_profile != "production":
        return
    actual = str(settings.spark_layout_parser or "").strip().lower()
    if actual != expected:
        raise RuntimeError(
            f"production_lock layout_parser mismatch: manifest={expected} settings={actual}"
        )


def _validate_require_gpu_rerank(manifest: ProductionLockManifest, spark_profile: str) -> None:
    if spark_profile == "test":
        return
    expected = manifest.required.get("require_gpu_rerank")
    if expected is None:
        return
    if not isinstance(expected, bool):
        raise RuntimeError("production_lock.required.require_gpu_rerank must be a boolean")
    if not expected:
        return
    if not manifest.enforcement.get("require_gpu_rerank"):
        return
    from spark.core.production_profile import ProductionProfile

    active = ProductionProfile.hardened_defaults()
    if not active.require_gpu_rerank:
        raise RuntimeError(
            "production_lock require_gpu_rerank mismatch: manifest=true profile=false"
        )


def _validate_degraded_rerank_policy(manifest: ProductionLockManifest) -> None:
    expected = str(manifest.required.get("degraded_rerank_policy") or "").strip().lower()
    if not expected:
        return
    if expected != "rank_gate":
        raise RuntimeError(
            f"production_lock degraded_rerank_policy must be rank_gate, got {expected!r}"
        )


def validate_app_layer_lock_at_startup(
    app_layer: AppLayerProductionLock | None,
    *,
    spark_profile: str,
) -> None:
    """Validate app-layer production gates from production_lock manifest."""
    from spark.core.config import settings

    if spark_profile.strip().lower() == "test" or app_layer is None:
        return
    if settings.app_env.strip().lower() != "production":
        return
    profile = settings.app_profile
    if app_layer.require_redis and not profile.redis_required:
        raise RuntimeError(
            "production_lock app_layer.require_redis=true but AppProfile.redis_required=false"
        )
    if app_layer.require_fail_closed_auth and not profile.fail_closed_on_missing_auth:
        raise RuntimeError(
            "production_lock app_layer.require_fail_closed_auth=true "
            "but AppProfile.fail_closed_on_missing_auth=false"
        )
    if app_layer.min_api_workers > 0:
        workers = int(os.environ.get("ONPREM_API_WORKERS", "2"))
        if workers < app_layer.min_api_workers:
            raise RuntimeError(
                f"ONPREM_API_WORKERS={workers} below production_lock minimum "
                f"{app_layer.min_api_workers}"
            )
    if app_layer.require_trust_ui_mapping:
        log.info(
            "production_lock_app_layer_trust_mapping",
            detail="enforced by tests/app_layer/contracts/test_frontend_trust_mapping.py",
        )


def _app_layer_v2_lock_enforced(*, spark_profile: str, app_env: str) -> bool:
    if spark_profile.strip().lower() == "test":
        return False
    if app_env.strip().lower() == "production":
        return True
    flag = os.environ.get("APP_LAYER_V2_LOCK", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def validate_app_layer_v2_lock_at_startup(
    app_layer_v2: AppLayerV2ProductionLock | None,
    *,
    spark_profile: str,
) -> None:
    """Validate app-layer v2 production gates (Phase 12)."""
    from spark.core.config import settings

    if app_layer_v2 is None:
        return
    if not _app_layer_v2_lock_enforced(
        spark_profile=spark_profile,
        app_env=settings.app_env,
    ):
        return

    profile = settings.app_profile

    if app_layer_v2.require_ticket_freshness_check and not profile.require_ticket_freshness_check:
        raise RuntimeError(
            "production_lock app_layer_v2.require_ticket_freshness_check=true "
            "but AppProfile.require_ticket_freshness_check=false"
        )
    if (
        app_layer_v2.forbid_system_principal_outside_test
        and profile.allow_system_principal_fallback
    ):
        raise RuntimeError(
            "production_lock app_layer_v2 forbids system principal fallback in production"
        )
    if app_layer_v2.min_sse_pool_size > 0:
        if settings.db_stream_pool_size < app_layer_v2.min_sse_pool_size:
            raise RuntimeError(
                f"db_stream_pool_size={settings.db_stream_pool_size} below "
                f"app_layer_v2 minimum {app_layer_v2.min_sse_pool_size}"
            )
    if app_layer_v2.max_sse_per_user > 0:
        if profile.sse_max_connections_per_user > app_layer_v2.max_sse_per_user:
            raise RuntimeError(
                f"sse_max_connections_per_user={profile.sse_max_connections_per_user} "
                f"exceeds app_layer_v2 max {app_layer_v2.max_sse_per_user}"
            )
    if app_layer_v2.require_audit_export_hmac and not os.environ.get("AUDIT_EXPORT_HMAC_SECRET"):
        raise RuntimeError(
            "AUDIT_EXPORT_HMAC_SECRET is required when app_layer_v2.require_audit_export_hmac=true"
        )

    if app_layer_v2.require_dual_admission:
        from spark.api.platform.route_policy import resolve_route_policy

        sse_policy = resolve_route_policy("GET", "/api/v1/alerts/stream")
        if sse_policy.admission_plane != "sse":
            raise RuntimeError("app_layer_v2 dual admission: alerts stream must use sse plane")

    if app_layer_v2.require_sse_connection_governor:
        from spark.services.streams import connection_governor as governor_mod

        if not hasattr(governor_mod, "connection_governor"):
            raise RuntimeError("app_layer_v2 requires connection_governor module")

    if app_layer_v2.require_atomic_redis_pop:
        from spark.core.cache import Cache

        if not hasattr(Cache, "atomic_pop_json"):
            raise RuntimeError("app_layer_v2 requires Cache.atomic_pop_json")

    if app_layer_v2.require_stream_completion_contract:
        root = _PROJECT_ROOT / "web" / "lib" / "streams" / "completion-contract.ts"
        if not root.is_file():
            raise RuntimeError("app_layer_v2 requires web stream completion contract module")

    log.info("production_lock_app_layer_v2_validated")
