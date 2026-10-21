"""Reusable OpenAPI error response definitions."""

from __future__ import annotations

from spark.schemas.openapi_examples import ERROR_404, ERROR_422, ERROR_503, ERROR_ENVELOPE

STANDARD_ERRORS: dict[int | str, dict[str, object]] = {
    404: {
        "description": "Resource not found",
        "content": {"application/json": {"example": ERROR_404}},
    },
    422: {
        "description": "Validation error",
        "content": {"application/json": {"example": ERROR_422}},
    },
    429: {
        "description": "Rate limit exceeded",
        "content": {"application/json": {"example": ERROR_ENVELOPE}},
    },
}

READ_ERRORS: dict[int | str, dict[str, object]] = {**STANDARD_ERRORS}
WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **STANDARD_ERRORS,
    503: {
        "description": "Dependency unavailable",
        "content": {"application/json": {"example": ERROR_503}},
    },
}
