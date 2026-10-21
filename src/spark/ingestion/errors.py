"""Ingest pipeline error taxonomy for Celery retry and DLQ routing."""

from __future__ import annotations

import httpx
from sqlalchemy.exc import DBAPIError, OperationalError

from spark.ingestion.reason_codes import ClassifiedReason, ReasonCode


class IngestionFailure(RuntimeError):
    """Pipeline failure with a stable reason code for operators and tests."""

    def __init__(self, reason_code: str, reason_detail: str) -> None:
        super().__init__(reason_detail)
        self.reason_code = reason_code
        self.reason_detail = reason_detail


class TransientIngestError(IngestionFailure):
    """Retryable ingest failure (network, timeout, transient infra)."""


class PermanentIngestError(IngestionFailure):
    """Non-retryable ingest failure (validation, config, permanent policy block)."""


def permanent_ingest_failure(reason_code: str | ReasonCode, reason_detail: str) -> PermanentIngestError:
    code = reason_code.value if isinstance(reason_code, ReasonCode) else reason_code
    return PermanentIngestError(code, reason_detail)


def transient_ingest_failure(reason_code: str | ReasonCode, reason_detail: str) -> TransientIngestError:
    code = reason_code.value if isinstance(reason_code, ReasonCode) else reason_code
    return TransientIngestError(code, reason_detail)


def _as_exception(classified: ClassifiedReason) -> Exception:
    if classified.transient:
        return TransientIngestError(classified.reason_code, classified.detail)
    return PermanentIngestError(classified.reason_code, classified.detail)


def classify_exception(exc: Exception) -> ClassifiedReason:
    """Map arbitrary exceptions to a structured reason (Phase 3)."""
    if isinstance(exc, (TransientIngestError, PermanentIngestError)):
        try:
            code = ReasonCode(exc.reason_code)
        except ValueError:
            code = ReasonCode.UNKNOWN
        return ClassifiedReason(code=code, detail=exc.reason_detail, transient=isinstance(exc, TransientIngestError))

    if isinstance(exc, IngestionFailure):
        try:
            code = ReasonCode(exc.reason_code)
        except ValueError:
            code = ReasonCode.PIPELINE_FAILED
        return ClassifiedReason(code=code, detail=exc.reason_detail, transient=code.is_transient)

    from spark.ingestion.config_resolver import ConfigError
    from spark.ingestion.parsers.base import ParserError

    if isinstance(exc, (ConfigError, FileNotFoundError)):
        return ClassifiedReason(
            code=ReasonCode.CONFIG_PROFILE_NOT_FOUND,
            detail=str(exc)[:2000],
            transient=False,
        )
    if isinstance(exc, ValueError):
        return ClassifiedReason(
            code=ReasonCode.VALIDATION_FAILED,
            detail=str(exc)[:2000],
            transient=False,
        )
    if isinstance(exc, ParserError):
        try:
            code = ReasonCode(exc.reason_code)
        except ValueError:
            code = ReasonCode.PIPELINE_FAILED
        return ClassifiedReason(code=code, detail=exc.reason_detail, transient=code.is_transient)

    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return ClassifiedReason(
            code=ReasonCode.STORAGE_READ_FAILED,
            detail=str(exc)[:2000],
            transient=True,
        )
    if isinstance(exc, httpx.TimeoutException):
        return ClassifiedReason(code=ReasonCode.QDRANT_TIMEOUT, detail=str(exc)[:2000], transient=True)
    if isinstance(exc, httpx.HTTPError):
        return ClassifiedReason(code=ReasonCode.QDRANT_UNAVAILABLE, detail=str(exc)[:2000], transient=True)
    if isinstance(exc, (OperationalError, DBAPIError)):
        return ClassifiedReason(code=ReasonCode.DB_TRANSIENT, detail=str(exc)[:2000], transient=True)

    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return ClassifiedReason(code=ReasonCode.QDRANT_TIMEOUT, detail=str(exc)[:2000], transient=True)
    if "qdrant" in msg and ("connect" in msg or "unavailable" in msg):
        return ClassifiedReason(code=ReasonCode.QDRANT_UNAVAILABLE, detail=str(exc)[:2000], transient=True)
    if "cuda" in msg or "out of memory" in msg or "oom" in msg:
        return ClassifiedReason(code=ReasonCode.EMBED_TRANSIENT, detail=str(exc)[:2000], transient=True)

    return ClassifiedReason(code=ReasonCode.UNKNOWN, detail=str(exc)[:2000], transient=False)


def classify_embed_exception(exc: Exception) -> ClassifiedReason:
    """Classify index-time embed failures — CUDA/OOM/timeout are transient."""
    from spark.ingestion.index.embed_retry import is_embed_transient

    if is_embed_transient(exc):
        return ClassifiedReason(
            code=ReasonCode.EMBED_TRANSIENT,
            detail=str(exc)[:2000],
            transient=True,
        )
    return classify_exception(exc)


def classify_pipeline_exception(exc: Exception) -> Exception:
    """Backward-compatible wrapper returning typed ingest exceptions."""
    return _as_exception(classify_exception(exc))


def policy_block_routes_to_dlq() -> bool:
    """True when content policy blocks land in DLQ per production lock."""
    from spark.ingestion.job_reliability import content_policy_block_job_status

    return content_policy_block_job_status() == "dlq"
