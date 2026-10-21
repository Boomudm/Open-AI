from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

import structlog

from spark.core.config import settings

_configured = False

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
factory_id_ctx: ContextVar[str | None] = ContextVar("factory_id", default=None)


_REDACT_KEYS = frozenset({
    "password", "secret", "token", "api_key", "apikey", "authorization",
    "jwt_secret", "postgres_password", "minio_root_password", "s3_secret_key",
    "google_client_secret", "langchain_api_key", "ollama_api_key",
    "hmac_secret", "cookie", "credentials",
})

_REDACT_SUBSTRINGS = ("password", "secret", "token", "apikey", "api_key", "credential")


def _redact_sensitive(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if key_lower in _REDACT_KEYS or any(s in key_lower for s in _REDACT_SUBSTRINGS):
            event_dict[key] = "***REDACTED***"
    return event_dict


def _merge_contextvars(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    for var, key in (
        (request_id_ctx, "request_id"),
        (user_id_ctx, "user_id"),
        (factory_id_ctx, "factory_id"),
    ):
        value = var.get()
        if value:
            event_dict[key] = value
    return event_dict


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            _merge_contextvars,
            _redact_sensitive,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def bind_request_context(
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    factory_id: str | None = None,
) -> None:
    if request_id is not None:
        request_id_ctx.set(request_id)
    if user_id is not None:
        user_id_ctx.set(user_id)
    if factory_id is not None:
        factory_id_ctx.set(factory_id)


def clear_request_context() -> None:
    request_id_ctx.set(None)
    user_id_ctx.set(None)
    factory_id_ctx.set(None)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
