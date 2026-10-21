"""Contract: Phase 0 — RAGKernel single execution path."""

from __future__ import annotations

import inspect

import pytest

from spark.retrieval.kernel import RAGKernel, RAGKernelInput, RAGKernelOutput, get_rag_kernel
from spark.retrieval.models import RAGResult
from spark.retrieval.service import RAGService


def test_rag_kernel_exports() -> None:
    assert callable(get_rag_kernel)
    kernel = get_rag_kernel()
    assert isinstance(kernel, RAGKernel)
    assert "run" in dir(kernel)


def test_rag_service_implements_kernel_executor() -> None:
    svc = RAGService()
    assert hasattr(svc, "execute_sync")
    assert hasattr(svc, "execute_stream")
    assert inspect.iscoroutinefunction(svc.execute_sync)


@pytest.mark.asyncio
async def test_query_delegates_to_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[RAGKernelInput] = []

    class _StubKernel:
        async def run(self, inp: RAGKernelInput, *, executor):
            calls.append(inp)
            yield RAGKernelOutput(
                result=RAGResult(
                    answer="ok",
                    sources=[],
                    used_filters={},
                    fallback_level=0,
                    intent="factual",
                    answer_path="grounded_llm",
                ),
                events=[],
            )

    monkeypatch.setattr("spark.retrieval.service.get_rag_kernel", lambda: _StubKernel())
    svc = RAGService()
    result = await svc.query("test question")
    assert result.answer == "ok"
    assert len(calls) == 1
    assert calls[0].stream is False


@pytest.mark.asyncio
async def test_query_stream_delegates_to_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[RAGKernelInput] = []

    class _StubKernel:
        async def run(self, inp: RAGKernelInput, *, executor):
            calls.append(inp)
            if False:
                yield ""

    monkeypatch.setattr("spark.retrieval.service.get_rag_kernel", lambda: _StubKernel())
    svc = RAGService()
    async for _ in svc.query_stream("stream question"):
        pass
    assert len(calls) == 1
    assert calls[0].stream is True
