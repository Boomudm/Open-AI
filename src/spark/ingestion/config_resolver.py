"""Resolved ingest configuration — profiles merged, validated, immutable per job."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.core.config import settings
from spark.core.llm_profile import embedding_dimension
from spark.ingestion.config_loader import load_config

_PROFILES_ROOT = Path(__file__).resolve().parents[3] / "configs"
_CHUNKING_PROFILES = _PROFILES_ROOT / "chunking_profiles.yaml"
_EMBEDDING_PROFILES = _PROFILES_ROOT / "embedding_profiles.yaml"


class ConfigError(ValueError):
    """Invalid or inconsistent ingest configuration."""


@dataclass(frozen=True)
class ChunkingParams:
    profile: str | None = None
    strategy: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int = 0
    mode: str | None = None
    separators: tuple[str, ...] | None = None
    parent_chunk_size: int | None = None
    parent_chunk_overlap: int | None = None
    child_chunk_size: int | None = None
    child_chunk_overlap: int | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.profile is not None:
            out["profile"] = self.profile
        if self.strategy is not None:
            out["strategy"] = self.strategy
        if self.chunk_size is not None:
            out["chunk_size"] = self.chunk_size
        if self.chunk_overlap:
            out["chunk_overlap"] = self.chunk_overlap
        if self.mode is not None:
            out["mode"] = self.mode
        if self.separators is not None:
            out["separators"] = list(self.separators)
        if self.parent_chunk_size is not None:
            out["parent_chunk_size"] = self.parent_chunk_size
        if self.parent_chunk_overlap is not None:
            out["parent_chunk_overlap"] = self.parent_chunk_overlap
        if self.child_chunk_size is not None:
            out["child_chunk_size"] = self.child_chunk_size
        if self.child_chunk_overlap is not None:
            out["child_chunk_overlap"] = self.child_chunk_overlap
        return out


@dataclass(frozen=True)
class EmbeddingParams:
    profile: str | None
    model: str | None
    provider: str | None
    expected_dim: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "model": self.model,
            "provider": self.provider,
            "expected_dim": self.expected_dim,
        }


@dataclass(frozen=True)
class ResolvedIngestConfig:
    document_type: str
    parser: str
    chunking: ChunkingParams
    embedding: EmbeddingParams
    default_route: str
    required_metadata: tuple[str, ...]
    raw: dict[str, Any]

    def expects_qdrant_output(self) -> bool:
        if self.default_route is None:
            return True
        return self.default_route in ("qdrant", "both")

    def config_hash(self) -> str:
        payload = {
            "document_type": self.document_type,
            "chunking": self.chunking.as_dict(),
            "embedding": self.embedding.as_dict(),
            "default_route": self.default_route,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()[:16]

    def get(self, key: str, default: Any = None) -> Any:
        if key == "chunking":
            return self.chunking.as_dict()
        if key == "embedding":
            return self.embedding.as_dict()
        return self.raw.get(key, default)

    @property
    def layout_parser(self) -> str | None:
        """Per-document-type PDF layout parser override (``layout.parser`` in
        the ingest YAML). Lets Thai text-layer docs opt out of docling, whose
        table model shreds Thai glyphs and drops narrative sections."""
        return (self.raw.get("layout") or {}).get("parser")


def get_chunking_config(config: ResolvedIngestConfig | dict[str, Any]) -> dict[str, Any]:
    """Return effective chunking params for parsers (resolved or legacy dict)."""
    if isinstance(config, ResolvedIngestConfig):
        return config.chunking.as_dict()
    return dict(config.get("chunking") or {})


@lru_cache(maxsize=8)
def _load_yaml_profiles(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"profile file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"invalid profile file (not a mapping): {path}")
    return data


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _merge_chunking_profile(
    chunking: dict[str, Any],
    *,
    profile_name: str | None = None,
) -> dict[str, Any]:
    name = profile_name or chunking.get("profile")
    if not name:
        return dict(chunking)
    profiles = _load_yaml_profiles(_CHUNKING_PROFILES)
    profile = profiles.get(name)
    if profile is None:
        raise ConfigError(f"config_profile_not_found: chunking profile {name!r}")
    if not isinstance(profile, dict):
        raise ConfigError(f"invalid chunking profile (not a mapping): {name!r}")
    merged = _deep_merge_dict(profile, chunking)
    merged["profile"] = name
    return merged


def _merge_embedding_profile(
    embedding: dict[str, Any],
    *,
    profile_name: str | None = None,
) -> EmbeddingParams:
    name = profile_name or embedding.get("profile")
    merged = dict(embedding)
    if name:
        profiles = _load_yaml_profiles(_EMBEDDING_PROFILES)
        profile = profiles.get(name)
        if profile is None:
            raise ConfigError(f"config_profile_not_found: embedding profile {name!r}")
        if not isinstance(profile, dict):
            raise ConfigError(f"invalid embedding profile (not a mapping): {name!r}")
        merged = _deep_merge_dict(profile, merged)
        merged["profile"] = name

    expected_dim = int(merged.get("expected_dim") or merged.get("dim") or 0)
    model = merged.get("model")
    provider = merged.get("provider")
    if not model or not provider or expected_dim <= 0:
        raise ConfigError(
            f"embedding profile {name!r} must define model, provider, and expected_dim"
        )

    active_dim = embedding_dimension()
    if expected_dim != active_dim:
        raise ConfigError(
            f"embedding profile {name!r} expected_dim={expected_dim} does not match "
            f"active LLM_PROFILE={settings.llm_profile!r} embed_dim={active_dim}. "
            "Re-ingest after aligning profiles or change LLM_PROFILE."
        )

    return EmbeddingParams(
        profile=str(name) if name else None,
        model=str(model),
        provider=str(provider),
        expected_dim=expected_dim,
    )


def _chunking_from_dict(data: dict[str, Any]) -> ChunkingParams:
    separators = data.get("separators")
    sep_tuple: tuple[str, ...] | None = None
    if separators is not None:
        sep_tuple = tuple(str(s) for s in separators)
    chunk_size = data.get("chunk_size")
    return ChunkingParams(
        profile=data.get("profile"),
        strategy=data.get("strategy"),
        chunk_size=int(chunk_size) if chunk_size is not None else None,
        chunk_overlap=int(data.get("chunk_overlap") or 0),
        mode=data.get("mode"),
        separators=sep_tuple,
        parent_chunk_size=(
            int(data["parent_chunk_size"]) if data.get("parent_chunk_size") is not None else None
        ),
        parent_chunk_overlap=(
            int(data["parent_chunk_overlap"])
            if data.get("parent_chunk_overlap") is not None
            else None
        ),
        child_chunk_size=(
            int(data["child_chunk_size"]) if data.get("child_chunk_size") is not None else None
        ),
        child_chunk_overlap=(
            int(data["child_chunk_overlap"])
            if data.get("child_chunk_overlap") is not None
            else None
        ),
    )


def resolve_ingest_config(
    document_type: str,
    factory_cfg: dict[str, Any] | None = None,
) -> ResolvedIngestConfig:
    """Load type YAML, merge chunking/embedding profiles, apply factory overrides."""
    base = deepcopy(load_config(document_type))
    factory_cfg = factory_cfg or {}
    ingest_overrides = factory_cfg.get("ingest") or {}

    chunking = dict(base.get("chunking") or {})
    chunk_profile_override = ingest_overrides.get("chunking_profile")
    if chunk_profile_override:
        merged_chunking = _merge_chunking_profile({"profile": str(chunk_profile_override)})
    else:
        merged_chunking = _merge_chunking_profile(chunking)

    embedding = dict(base.get("embedding") or {})
    if not embedding:
        embedding = {"profile": "default_th"}
    embed_profile_override = ingest_overrides.get("embedding_profile")
    embedding_params = _merge_embedding_profile(
        embedding,
        profile_name=str(embed_profile_override) if embed_profile_override else None,
    )

    raw = deepcopy(base)
    raw["chunking"] = merged_chunking
    raw["embedding"] = embedding_params.as_dict()

    required = base.get("required_metadata") or []
    if not isinstance(required, list):
        raise ConfigError(f"required_metadata must be a list for {document_type}")

    return ResolvedIngestConfig(
        document_type=document_type,
        parser=str(base.get("parser") or ""),
        chunking=_chunking_from_dict(merged_chunking),
        embedding=embedding_params,
        default_route=str(base.get("default_route") or "qdrant"),
        required_metadata=tuple(str(x) for x in required),
        raw=raw,
    )


def clear_profile_caches() -> None:
    _load_yaml_profiles.cache_clear()
