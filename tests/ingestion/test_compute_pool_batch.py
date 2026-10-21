"""Phase 5 — ingest compute pool batch encode."""

from __future__ import annotations


import pytest
from qdrant_client.models import SparseVector

from spark.ingestion.index.compute_pool import IngestComputePool


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    IngestComputePool.reset_for_tests()
    yield
    IngestComputePool.reset_for_tests()


@pytest.mark.asyncio
async def test_encode_dense_batch_uses_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = IngestComputePool.get()
    seen: list[str] = []

    def _fake_dense(texts: list[str]) -> list[list[float]]:
        seen.append("dense")
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr("spark.ingestion.index.compute_pool.encode_dense_sync", _fake_dense)
    out = await pool.encode_dense_batch(["a", "b"])
    assert len(out) == 2
    assert seen == ["dense"]


@pytest.mark.asyncio
async def test_encode_sparse_batch_uses_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = IngestComputePool.get()
    seen: list[str] = []

    def _fake_sparse(texts: list[str]) -> list[SparseVector]:
        seen.append("sparse")
        return [SparseVector(indices=[1], values=[1.0]) for _ in texts]

    monkeypatch.setattr("spark.ingestion.index.compute_pool.encode_sparse_sync_batch", _fake_sparse)
    out = await pool.encode_sparse_batch(["a", "b"])
    assert len(out) == 2
    assert seen == ["sparse"]


@pytest.mark.asyncio
async def test_embed_retry_recovers_from_transient_oom(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.ingestion.index import embed_retry

    attempts = 0

    async def _flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("CUDA out of memory")
        return "ok"

    async def _instant_sleep(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("spark.ingestion.index.embed_retry.asyncio.sleep", _instant_sleep)
    result = await embed_retry.with_embed_retry(_flaky, max_attempts=3)
    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_embed_retry_exhaustion_raises_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.ingestion.errors import TransientIngestError
    from spark.ingestion.index import embed_retry

    async def _always_oom() -> None:
        raise RuntimeError("CUDA OOM")

    async def _instant_sleep(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("spark.ingestion.index.embed_retry.asyncio.sleep", _instant_sleep)
    with pytest.raises(TransientIngestError) as exc_info:
        await embed_retry.with_embed_retry(_always_oom, max_attempts=2)
    assert exc_info.value.reason_code == "embed_transient"
