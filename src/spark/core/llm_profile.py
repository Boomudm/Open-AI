from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.core.config import settings

_PROFILES_PATH = Path(__file__).resolve().parents[3] / "configs" / "llm_profiles.yaml"

_ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _interpolate_env(value: Any) -> Any:
    """Expand ``${VAR}`` references from the environment.

    Lets profiles keep secrets (e.g. gateway API keys) in ``.env`` instead of the
    git-tracked YAML: ``api_key: ${KKU_API_KEY}``.
    """
    if isinstance(value, str):
        return _ENV_REF_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


@lru_cache(maxsize=8)
def load_llm_profile(name: str | None = None) -> dict[str, Any]:
    profile_name = name or settings.llm_profile
    if not _PROFILES_PATH.exists():
        return {}
    with _PROFILES_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid LLM profiles file: {_PROFILES_PATH}")
    profile = data.get(profile_name)
    if profile is None:
        raise KeyError(f"LLM profile not found: {profile_name}")
    if not isinstance(profile, dict):
        raise ValueError(f"Invalid LLM profile (not a mapping): {profile_name}")
    return _interpolate_env(profile)


_BGE_M3_GATEWAY_ALIASES = frozenset({"bge-m3", "bge_m3"})


def sparse_tokenizer_model(name: str | None = None) -> str:
    """HuggingFace tokenizer id for BGE-M3 sparse leg.

    OpenAI-compatible gateways expose dense embed as ``bge-m3``; sparse encoding
    still needs the full ``BAAI/bge-m3`` tokenizer locally.
    """
    try:
        profile = load_llm_profile(name)
    except (KeyError, ValueError):
        profile = {}
    explicit = profile.get("sparse_embed_model") or profile.get("sparse_tokenizer_model")
    if explicit:
        return str(explicit)
    embed_model = str(profile.get("embed_model") or settings.ollama_embed_model)
    if embed_model in _BGE_M3_GATEWAY_ALIASES:
        return "BAAI/bge-m3"
    return embed_model


def embedding_dimension(name: str | None = None) -> int:
    """Return embedding vector size from the active profile, with settings fallback."""
    try:
        profile = load_llm_profile(name)
    except (KeyError, ValueError):
        profile = {}
    raw = profile.get("embed_dim") or settings.ollama_embed_dim
    dim = int(raw)
    if dim <= 0:
        raise ValueError(f"Invalid embedding dimension: {raw}")
    return dim
