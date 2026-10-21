"""Ingest error classification tests (Phase 2 retry policy)."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError

from spark.ingestion.errors import (
    PermanentIngestError,
    TransientIngestError,
    classify_exception,
    classify_pipeline_exception,
)
from spark.ingestion.reason_codes import ReasonCode


def test_operational_error_is_transient() -> None:
    exc = OperationalError("stmt", {}, Exception("connection reset"))
    classified = classify_exception(exc)
    assert classified.code == ReasonCode.DB_TRANSIENT
    assert classified.transient is True
    wrapped = classify_pipeline_exception(exc)
    assert isinstance(wrapped, TransientIngestError)


def test_unknown_error_is_permanent() -> None:
    classified = classify_exception(RuntimeError("something unexpected"))
    assert classified.code == ReasonCode.UNKNOWN
    assert classified.transient is False
    wrapped = classify_pipeline_exception(RuntimeError("something unexpected"))
    assert isinstance(wrapped, PermanentIngestError)


def test_value_error_is_validation_failed() -> None:
    classified = classify_exception(ValueError("bad metadata"))
    assert classified.code == ReasonCode.VALIDATION_FAILED
    assert classified.transient is False
