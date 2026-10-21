"""Production profile — hardened defaults for pre-production cutover (Phase 0)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SparkProfile = Literal["test", "production", "dev"]
LexicalEngine = Literal["postgres_thai_v3"]
SparseEncoderKind = Literal["bge_m3", "splade_v3", "none"]

_VALID_LEXICAL_ENGINES: frozenset[str] = frozenset({"postgres_thai_v3"})
_VALID_SPARSE_ENCODERS: frozenset[str] = frozenset({"bge_m3", "splade_v3", "none"})
_SECURITY_BOOL_KEYS: frozenset[str] = frozenset(
    {
        "ingest_policy_enabled",
        "rag_circuit_enabled",
        "query_rewrite_enabled",
        "extractive_first_for_safety_types",
        "extractive_first_for_procedure",
        "sparse_vectors_enabled",
    }
)


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_lexical_engine(value: Any, default: LexicalEngine) -> LexicalEngine:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in _VALID_LEXICAL_ENGINES:
        return normalized  # type: ignore[return-value]
    # Phase 6 wires postgres_thai_v3; until then map unknown to default target.
    if normalized in {"legacy", "opensearch", "postgres_v2"}:
        return "postgres_thai_v3"
    return default


def _coerce_sparse_encoder(value: Any, default: SparseEncoderKind) -> SparseEncoderKind:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in _VALID_SPARSE_ENCODERS:
        return normalized  # type: ignore[return-value]
    if normalized in {"hash_sparse_legacy", "hash", "legacy"}:
        return "bge_m3"
    return default


def resolve_lexical_engine_for_retrieval(engine: LexicalEngine) -> str:
    """Return registered retriever id (Phase 6: postgres_thai_v3 only)."""
    return engine


@dataclass(frozen=True)
class ProductionProfile:
    """Runtime profile merged from SPARK_PROFILE + optional factory overrides.

    Extractive-first flags remain in the profile for compatibility only. Answer
    production always uses grounded LLM generation.
    """

    ingest_policy_enabled: bool = True
    rag_circuit_enabled: bool = True
    lexical_engine: LexicalEngine = "postgres_thai_v3"
    query_rewrite_enabled: bool = True
    extractive_first_for_safety_types: bool = False
    extractive_first_for_procedure: bool = False
    sparse_vectors_enabled: bool = True
    sparse_encoder: SparseEncoderKind = "bge_m3"
    require_gpu_rerank: bool = True
    ml_classifier_enabled: bool = True

    @property
    def extractive_first_enabled(self) -> bool:
        """Compatibility shim: extractive-first is disabled for answer production."""
        return False

    @classmethod
    def hardened_defaults(cls) -> ProductionProfile:
        return cls()

    @classmethod
    def test_defaults(cls) -> ProductionProfile:
        """Relaxed gates for CI deterministic runs only."""
        return cls(
            ingest_policy_enabled=False,
            rag_circuit_enabled=False,
            lexical_engine="postgres_thai_v3",
            query_rewrite_enabled=False,
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
            sparse_vectors_enabled=False,
            sparse_encoder="none",
            require_gpu_rerank=False,
            ml_classifier_enabled=False,
        )

    @classmethod
    def from_settings(cls) -> ProductionProfile:
        from spark.core.config import settings

        profile = settings.spark_profile.strip().lower()
        if profile == "test":
            base = cls.test_defaults()
            return cls(
                ingest_policy_enabled=_coerce_bool(
                    settings.spark_ingest_policy_enabled, base.ingest_policy_enabled
                ),
                rag_circuit_enabled=_coerce_bool(
                    settings.spark_rag_circuit_enabled, base.rag_circuit_enabled
                ),
                lexical_engine=_coerce_lexical_engine(
                    settings.spark_lexical_engine, base.lexical_engine
                ),
                query_rewrite_enabled=base.query_rewrite_enabled,
                extractive_first_for_safety_types=False,
                extractive_first_for_procedure=False,
                sparse_vectors_enabled=not settings.sparse_vectors_disabled,
                sparse_encoder="none" if settings.sparse_vectors_disabled else "bge_m3",
                # Explicit: omitting these lets the dataclass defaults (True)
                # silently override test_defaults(), re-enabling the GPU-rerank
                # startup gate in CI.
                require_gpu_rerank=base.require_gpu_rerank,
                ml_classifier_enabled=base.ml_classifier_enabled,
            )
        base = cls.hardened_defaults()
        if not settings.spark_query_rewrite_llm_enabled:
            from dataclasses import replace as _dc_replace
            return _dc_replace(base, query_rewrite_enabled=False)
        return base

    @classmethod
    def for_factory(cls, config: dict[str, Any]) -> ProductionProfile:
        """Merge factory `features` (or legacy `remediation`) over env/profile defaults."""
        base = cls.from_settings()
        override = config.get("features") or config.get("remediation") or {}
        if not isinstance(override, dict):
            return base
        merged = cls(
            ingest_policy_enabled=_merge_security_bool(
                base.ingest_policy_enabled,
                override.get("ingest_policy_enabled"),
            ),
            rag_circuit_enabled=_merge_security_bool(
                base.rag_circuit_enabled,
                override.get("rag_circuit_enabled"),
            ),
            lexical_engine=_coerce_lexical_engine(
                override.get("lexical_engine"), base.lexical_engine
            ),
            query_rewrite_enabled=_merge_security_bool(
                base.query_rewrite_enabled,
                override.get("query_rewrite_enabled"),
            ),
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
            sparse_vectors_enabled=_merge_security_bool(
                base.sparse_vectors_enabled,
                override.get("sparse_vectors_enabled"),
            ),
            sparse_encoder=_coerce_sparse_encoder(
                override.get("sparse_encoder"), base.sparse_encoder
            ),
        )
        return merged

    def as_dict(self) -> dict[str, Any]:
        return {
            "ingest_policy_enabled": self.ingest_policy_enabled,
            "rag_circuit_enabled": self.rag_circuit_enabled,
            "lexical_engine": self.lexical_engine,
            "query_rewrite_enabled": self.query_rewrite_enabled,
            "extractive_first_for_safety_types": self.extractive_first_for_safety_types,
            "extractive_first_for_procedure": self.extractive_first_for_procedure,
            "extractive_first_enabled": self.extractive_first_enabled,
            "sparse_vectors_enabled": self.sparse_vectors_enabled,
            "sparse_encoder": self.sparse_encoder,
            "require_gpu_rerank": self.require_gpu_rerank,
            "ml_classifier_enabled": self.ml_classifier_enabled,
        }


def _merge_security_bool(base: bool, override: Any) -> bool:
    """Factory overrides may tighten (False→True) but never disable security when base is on."""
    if override is None:
        return base
    new = _coerce_bool(override, base)
    if base and not new:
        return True
    return new


# Back-compat alias — remove in Phase 13 teardown.
RemediationFlags = ProductionProfile
