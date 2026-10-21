"""Generation input/output types (Phase 10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from spark.retrieval.models import RetrievedDoc

if TYPE_CHECKING:
    from spark.retrieval.deadline import RequestDeadline

GenerationMode = Literal[
    "extractive",
    "paraphrase",
    "grounded_llm",
    "no_data",
    "llm_unavailable",
]


@dataclass(frozen=True)
class GroundedGenerateResult:
    answer: str
    cited_docs: list[RetrievedDoc]
    answer_path: str
    citations_verified: bool
    generation_mode: GenerationMode = "no_data"
    llm_usage: dict[str, Any] | None = None


@dataclass
class GenerationInput:
    question: str
    docs: list[RetrievedDoc]
    llm: Any
    chat_history: list[tuple[str, str]] | None = None
    synthesis_question: str | None = None
    force_extractive_first: bool | None = None
    deadline: RequestDeadline | None = None
    cancel_event: Any | None = None
    prompt_template: Any | None = None
    llm_usage_calls: list[dict[str, Any]] = field(default_factory=list)

    def intent_requires_extractive(self) -> bool:
        """Compatibility shim: answer production no longer uses extractive-first."""
        return False

    def should_extractive_first(self) -> bool:
        return False


@dataclass
class GenerationOutput:
    result: GroundedGenerateResult
    spans_used: int = 0
    events: list[str] = field(default_factory=list)
