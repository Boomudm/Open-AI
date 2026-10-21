"""API platform layer — gateway middleware, errors, admission (app-layer remediation)."""

from __future__ import annotations

__all__ = ["register_exception_handlers", "register_platform_middleware"]


def __getattr__(name: str):
    if name == "register_exception_handlers":
        from spark.api.platform.errors import register_exception_handlers

        return register_exception_handlers
    if name == "register_platform_middleware":
        from spark.api.platform.middleware.stack import register_platform_middleware

        return register_platform_middleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
