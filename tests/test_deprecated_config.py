"""Deprecated config audit at startup."""

from __future__ import annotations

import os

from spark.core.deprecated_config import audit_deprecated_config
from spark.core.metrics import deprecated_config_usage_total


def test_audit_deprecated_ragflow_env(monkeypatch) -> None:
    monkeypatch.setenv("RAGFLOW_API_URL", "http://legacy:9380")
    before = deprecated_config_usage_total.labels(key="RAGFLOW_API_URL")._value.get()  # type: ignore[attr-defined]
    audit_deprecated_config()
    after = deprecated_config_usage_total.labels(key="RAGFLOW_API_URL")._value.get()  # type: ignore[attr-defined]
    assert after >= before + 1


def test_audit_deprecated_ingest_backend(monkeypatch) -> None:
    monkeypatch.setenv("INGEST_BACKEND", "auto")
    audit_deprecated_config()
    assert os.environ.get("INGEST_BACKEND") == "auto"
