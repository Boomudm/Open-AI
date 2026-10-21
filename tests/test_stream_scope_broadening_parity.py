"""Stream/sync kernel parity for scope broadening (Phase 10)."""

from __future__ import annotations

import pytest

from spark.retrieval.kernel import RAGKernelOutput
from spark.retrieval.models import RAGFilter, RAGResult
from spark.retrieval.service import RAGService


@pytest.mark.asyncio
async def test_query_stream_passes_allow_scope_broadening_to_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, bool] = {}

    class _FakeKernel:
        async def run(self, inp, executor):
            captured["allow_scope_broadening"] = inp.allow_scope_broadening
            yield RAGKernelOutput(
                result=RAGResult(
                    answer="ok",
                    sources=[],
                    fallback_level=2,
                    retrieval_report={"degraded": False},
                )
            )

    monkeypatch.setattr(
        "spark.retrieval.service.get_rag_kernel",
        lambda: _FakeKernel(),
    )

    result = None
    async for item in RAGService().query_stream(
        "test question",
        RAGFilter(factory_id="F-01"),
        allow_scope_broadening=True,
    ):
        if isinstance(item, RAGResult):
            result = item
        elif isinstance(item, RAGKernelOutput):
            result = item.result

    assert captured.get("allow_scope_broadening") is True
    assert result is not None


@pytest.mark.asyncio
async def test_query_stream_impl_passes_known_machines_to_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The streaming retrieval path must load the factory machine registry and
    pass it to _resolve_retrieval, or the cross-machine conflict guard is a
    no-op for alpha-only machine IDs (MC-GOLDEN-KSS) — letting another
    machine's manual answer the question. Parity with the non-stream _query_impl.
    """
    from spark.retrieval.service import _EarlyRAGResult

    captured: dict[str, object] = {}

    async def _fake_load(factory_id):
        captured["load_arg"] = factory_id
        return {"MC-GOLDEN-KSS", "MC-GOLDEN-SERVO"}

    async def _fake_resolve(self, *args, **kwargs):
        captured["known_factory_machines"] = kwargs.get("known_factory_machines")
        return _EarlyRAGResult(result=RAGResult(answer="ok"))

    monkeypatch.setattr(
        "spark.retrieval.service._load_factory_machine_ids", _fake_load
    )
    monkeypatch.setattr(RAGService, "_resolve_retrieval", _fake_resolve)

    async for _ in RAGService()._query_stream_impl(
        "servo motor MC-GOLDEN-SERVO มีสเปกกำลังไฟเท่าไหร่",
        RAGFilter(factory_id="F-GOLDEN"),
        6,
        0.0,
        None,
    ):
        pass

    assert captured.get("load_arg") == "F-GOLDEN"
    assert captured.get("known_factory_machines") == {"MC-GOLDEN-KSS", "MC-GOLDEN-SERVO"}
