"""Shared pytest fixtures — dispose async engine between tests to avoid loop conflicts."""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "1")
os.environ.setdefault("SPARK_TESTING", "1")
os.environ.setdefault("SPARK_PROFILE", "test")
os.environ.setdefault("SPARK_ALLOW_SYSTEM_PRINCIPAL", "1")

# aarch64/glibc: torch's libc10 and sklearn's bundled libgomp need static TLS.
# If they are dlopen'd late — after hundreds of test imports have consumed
# glibc's static-TLS surplus — they die with "cannot allocate memory in static
# TLS block". Importing them first, while surplus remains, is the reliable fix
# on this Jetson (LD_PRELOAD/GLIBC_TUNABLES alone were not enough).
try:  # pragma: no cover - environment shim
    import torch  # noqa: F401,E402
except Exception:
    pass
try:  # pragma: no cover - environment shim
    import sklearn  # noqa: F401,E402
except Exception:
    pass

import pytest

from spark.core.database import engine


@pytest.fixture(autouse=True)
async def _dispose_async_engine_after_test() -> None:
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def _spark_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default test suite uses relaxed SPARK_PROFILE=test (Phase 0)."""
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "test")


@pytest.fixture(autouse=True)
def _disable_cross_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never load the ~600MB cross-encoder."""
    from spark.retrieval.rerank.cross_encoder import cross_encoder

    monkeypatch.setattr(cross_encoder, "_init_fail_count", cross_encoder._MAX_INIT_RETRIES)
    monkeypatch.setattr(cross_encoder, "_encoder", None)


def fake_embed_profile(*, dimension: int | None = None):
    """Minimal EmbedProfile for ingest/router test doubles."""
    from spark.core.llm_profile import embedding_dimension
    from spark.ingestion.embed_profile import EmbedProfile

    dim = dimension if dimension is not None else embedding_dimension()
    return EmbedProfile(
        model_id="test-embed",
        provider="ollama",
        dimension=dim,
        llm_profile="test",
    )


@pytest.fixture(autouse=True)
def _reset_ingest_compute_pool_after_test() -> None:
    yield
    from spark.ingestion.index.compute_pool import IngestComputePool

    IngestComputePool.reset_for_tests()
