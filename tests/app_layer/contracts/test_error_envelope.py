"""Unified API error envelope contract (Phase 0 / 12)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spark.api.platform.errors import register_exception_handlers
from spark.main import app


def test_404_returns_standard_envelope(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "auth_required", False)
    client = TestClient(app)
    response = client.get("/this-route-does-not-exist-phase0")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "trace_id" in body
    assert isinstance(body["trace_id"], str)
    assert len(body["trace_id"]) >= 8
    assert "retryable" in body
    assert response.headers.get("X-Request-ID") == body["trace_id"]


def test_422_returns_standard_envelope() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["retryable"] is False
    assert "trace_id" in body


def test_500_returns_standard_envelope_without_leaking_internals() -> None:
    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.get("/boom")
    async def boom() -> None:
        raise RuntimeError("super secret stack detail")

    client = TestClient(probe, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["detail"] == "internal server error"
    assert "super secret" not in body["detail"]
    assert "trace_id" in body
    assert body["retryable"] is True
