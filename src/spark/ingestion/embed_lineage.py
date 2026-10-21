"""Runtime-derived embedding lineage for PG ↔ Qdrant chunk audit (remediation v2 Phase 1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from spark.ingestion.embed_profile import EmbedProfile

CHUNK_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class EmbedLineage:
    embed_model_id: str
    embed_model_version: str
    embed_provider: str
    embed_dimension: int
    chunk_schema_version: int
    config_hash: str

    def to_payload_fields(self) -> dict[str, str | int]:
        return {
            "embed_model_id": self.embed_model_id,
            "embed_model": self.embed_model_id,
            "embed_model_version": self.embed_model_version,
            "embed_provider": self.embed_provider,
            "embed_dimension": self.embed_dimension,
            "chunk_schema_version": self.chunk_schema_version,
            "config_hash": self.config_hash,
        }


def content_hash_for_text(text: str) -> str:
    """32-char content fingerprint (md5 hex) for mirror drift checks."""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def lineage_from_profile(profile: EmbedProfile, config_hash: str) -> EmbedLineage:
    """Build lineage metadata from the active embed profile at index time."""
    return EmbedLineage(
        embed_model_id=profile.model_id,
        embed_model_version=profile.version,
        embed_provider=profile.provider,
        embed_dimension=profile.dimension,
        chunk_schema_version=CHUNK_SCHEMA_VERSION,
        config_hash=config_hash or "unknown",
    )


def embed_lineage_for_text(
    text: str,
    *,
    profile: EmbedProfile | None = None,
    config_hash: str = "",
) -> dict[str, str | int]:
    """Return runtime embed lineage and content hash for a chunk embed input."""
    resolved = profile or EmbedProfile.from_runtime()
    lineage = lineage_from_profile(resolved, config_hash)
    payload = lineage.to_payload_fields()
    payload["content_hash"] = content_hash_for_text(text)
    return payload


def assert_retrieval_compatible(payload: dict, *, expected: EmbedLineage | None = None) -> bool:
    """True when a Qdrant payload matches the expected embed lineage tuple."""
    lineage = expected or lineage_from_profile(EmbedProfile.from_runtime(), "")
    if payload.get("embed_model_id") != lineage.embed_model_id:
        return False
    if payload.get("embed_model_version") != lineage.embed_model_version:
        return False
    stored_provider = payload.get("embed_provider")
    if stored_provider is not None and stored_provider != lineage.embed_provider:
        return False
    stored_schema = payload.get("chunk_schema_version")
    if stored_schema is not None and int(stored_schema) != lineage.chunk_schema_version:
        return False
    return True
