"""Native-only ingest backend (Phase 1)."""

from __future__ import annotations

from spark.ingestion.constants import INGEST_BACKEND
from spark.services.factory_config_service import FactoryConfigService


def test_ingest_backend_constant_is_native() -> None:
    assert INGEST_BACKEND == "native"


def test_factory_config_service_ingest_backend_always_native() -> None:
    svc = FactoryConfigService()
    assert svc.ingest_backend({}) == "native"
    assert svc.ingest_backend({"ingest": {"backend": "ragflow"}}) == "native"
    assert svc.ingest_backend({"ingest": {"backend": "auto"}}) == "native"
