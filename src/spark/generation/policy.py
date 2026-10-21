"""Generation policy resolution from ProductionProfile (Phase 10)."""

from __future__ import annotations

from dataclasses import dataclass

from spark.core.production_profile import ProductionProfile
from spark.retrieval.models import RAGFilter
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent


@dataclass(frozen=True)
class GenerationPolicy:
    extractive_first_for_safety_types: bool
    extractive_first_for_procedure: bool
    structured_safety_for_loto: bool = True

    @property
    def extractive_first_enabled(self) -> bool:
        return False

    def force_extractive(self, question: str) -> bool:
        """Compatibility shim: all document-grounded answers go through LLM generation."""
        return False

    def requires_structured_safety(self, question: str) -> bool:
        if not self.structured_safety_for_loto:
            return False
        return detect_safety_intent(question).kind != SafetyIntentKind.NONE


async def resolve_generation_policy(rf: RAGFilter | None) -> GenerationPolicy:
    from spark.core.database import AsyncSessionLocal
    from spark.services.factory_config_service import factory_config_service

    if rf and rf.factory_id:
        async with AsyncSessionLocal() as session:
            factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
        profile = ProductionProfile.for_factory(factory_cfg)
    else:
        profile = ProductionProfile.from_settings()

    return GenerationPolicy(
        extractive_first_for_safety_types=profile.extractive_first_for_safety_types,
        extractive_first_for_procedure=profile.extractive_first_for_procedure,
        structured_safety_for_loto=True,
    )
