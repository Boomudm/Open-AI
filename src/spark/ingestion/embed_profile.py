"""Runtime embedding model identity — single source of truth for lineage and filters."""

from __future__ import annotations

from dataclasses import dataclass

from spark.core.config import settings
from spark.core.llm_profile import embedding_dimension, load_llm_profile


@dataclass(frozen=True)
class EmbedProfile:
    model_id: str
    provider: str
    dimension: int
    llm_profile: str

    @property
    def version(self) -> str:
        """Stable version string stored in vector payloads and retrieval filters.

        Identifies the EMBEDDING (model + provider + dimension) — never the
        chat/LLM profile name. Baking the profile name in meant switching the
        chat model (demo -> gateway) silently blanked all vector retrieval
        even though every stored vector was produced by the exact same
        embedder. Changing anything in this string still requires re-ingest
        (or a payload migration) — see docs/runbooks.
        """
        return f"{self.model_id}@{self.provider}#{self.dimension}"

    @classmethod
    def from_runtime(cls, llm_profile_name: str | None = None) -> EmbedProfile:
        name = llm_profile_name or settings.llm_profile
        try:
            profile = load_llm_profile(name)
        except (KeyError, ValueError):
            profile = {}
        provider = str(
            profile.get("embed_provider") or profile.get("provider") or "ollama"
        ).lower()
        model_id = str(profile.get("embed_model") or settings.ollama_embed_model)
        return cls(
            model_id=model_id,
            provider=provider,
            dimension=embedding_dimension(name),
            llm_profile=name,
        )
