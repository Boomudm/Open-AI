"""Safety/procedure queries no longer attempt extractive-first."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.core.production_profile import ProductionProfile
from spark.generation.pipeline import generate
from spark.generation.types import GenerationInput, GroundedGenerateResult
from spark.retrieval.models import RetrievedDoc


def _doc(text: str) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": str(uuid.uuid4()),
            "document_type": "sop",
            "source_file": "sop.pdf",
            "page": 1,
        },
    )


@pytest.mark.asyncio
async def test_loto_question_uses_structured_grounded_llm_when_profile_flags_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loto_doc = _doc(
        "LOTO procedure: 1) Notify supervisor 2) Shut down machine 3) Isolate energy "
        "4) Apply lock and tag 5) Verify zero energy before maintenance."
    )
    monkeypatch.setattr(
        ProductionProfile,
        "from_settings",
        classmethod(lambda cls: ProductionProfile(
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
        )),
    )

    async def fake_structured_safety(_inp: GenerationInput) -> GroundedGenerateResult:
        return GroundedGenerateResult(
            answer="1. Notify supervisor before maintenance",
            cited_docs=[loto_doc],
            answer_path="grounded_structured_safety",
            citations_verified=True,
            generation_mode="grounded_llm",
        )

    monkeypatch.setattr(
        "spark.generation.pipeline.run_constrained_safety",
        fake_structured_safety,
    )
    monkeypatch.setattr(
        "spark.generation.pipeline.apply_nli_gate",
        lambda _q, result, **_: result,
    )

    class ExplodingLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("fallback grounded LLM should not run when structured safety succeeds")

    inp = GenerationInput(
        question="ขั้นตอน LOTO ก่อนซ่อมเครื่อง MC-001",
        docs=[loto_doc],
        llm=ExplodingLLM(),
    )
    out = await generate(inp)
    assert out.result.answer_path == "grounded_structured_safety"
    assert out.result.generation_mode == "grounded_llm"
    assert out.result.citations_verified is True


@pytest.mark.asyncio
async def test_procedure_intent_uses_grounded_llm_without_profile_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _doc("Step 1: Open guard. Step 2: Inspect belt tension. Step 3: Close guard.")
    cid = doc.payload["chunk_id"]
    monkeypatch.setattr(
        ProductionProfile,
        "from_settings",
        classmethod(lambda cls: ProductionProfile(
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
        )),
    )

    from spark.retrieval.safety.retrieval_verifier import VerificationResult

    monkeypatch.setattr(
        "spark.retrieval.safety.retrieval_verifier.verify_retrieval",
        AsyncMock(return_value=VerificationResult(
            action="accept",
            relevant_docs=[doc],
            relevant_count=1,
            partial_count=0,
            irrelevant_count=0,
            confidence=1.0,
        )),
    )

    class GroundedLLM:
        async def ainvoke(self, *_args, **_kwargs):
            class Response:
                # Thai answer for the Thai question — this test targets the
                # procedure-intent path, not the language gate.
                content = f"เปิดการ์ด ตรวจสอบความตึงสายพาน แล้วปิดการ์ด [chunk_id:{cid}]"

            return Response()

    inp = GenerationInput(
        question="ขั้นตอนตรวจสอบสายพาน MC-002 ทำอย่างไร",
        docs=[doc],
        llm=GroundedLLM(),
    )
    out = await generate(inp)
    assert out.result.generation_mode == "grounded_llm"
    assert out.result.answer_path == "grounded_llm"
    assert out.result.citations_verified is True
