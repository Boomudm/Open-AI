"""API platform middleware stack tests (Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spark.compliance.export_gate import check_export_rate_limit
from spark.main import app


@pytest.fixture(autouse=True)
def _disable_auth_for_middleware_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_security_headers_on_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Request-ID")


def test_global_rate_limit_returns_envelope(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    counts = {"n": 0}

    async def fake_increment(_key: str, *, window_sec: int = 60) -> int:
        counts["n"] += 1
        return counts["n"]

    monkeypatch.setattr(
        "spark.api.platform.middleware.rate_limit.increment_sliding_window",
        fake_increment,
    )
    monkeypatch.setattr(
        "spark.api.platform.middleware.rate_limit.global_rate_limit_rpm",
        lambda: 2,
    )
    monkeypatch.setattr(
        "spark.api.platform.middleware.rate_limit.global_rate_limit_burst",
        lambda: 0,
    )
    for _ in range(2):
        ok = client.get("/this-path-rate-limit-phase1")
        assert ok.status_code == 404
    blocked = client.get("/this-path-rate-limit-phase1")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limit_exceeded"
    assert body["retryable"] is True
    assert "trace_id" in body
    assert blocked.headers.get("Retry-After") == "60"
    assert blocked.headers.get("X-Request-ID") == body["trace_id"]


def test_health_paths_exempt_from_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spark.api.platform.middleware.rate_limit.global_rate_limit_rpm",
        lambda: 1,
    )
    for _ in range(5):
        response = client.get("/healthz")
        assert response.status_code == 200


def test_404_includes_trace_id(client: TestClient) -> None:
    response = client.get("/missing-route-phase1-test")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "trace_id" in body


@pytest.mark.asyncio
async def test_export_rate_limit_shared_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from spark.compliance import export_gate

    counts: dict[str, int] = {}

    async def fake_increment(key: str, *, window_sec: int = 3600) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(export_gate, "increment_sliding_window", fake_increment)
    monkeypatch.setattr(
        export_gate,
        "export_settings",
        lambda: {"rate_limit_per_user_hour": 1},
    )
    user = "user-export-phase1-test"
    await check_export_rate_limit(user)
    with pytest.raises(HTTPException) as exc_info:
        await check_export_rate_limit(user)
    assert exc_info.value.status_code == 429


def test_no_adhoc_429_in_endpoint_modules() -> None:
    """429 must come from platform/admission or domain rate modules — not raw endpoints."""
    root = Path(__file__).resolve().parents[1]
    endpoints_dir = root / "src" / "spark" / "api" / "v1" / "endpoints"
    allowlist = (
        "rate_limit",
        "admission",
        "export_gate",
        "ingest_rate_limit",
    )
    violations: list[str] = []
    for path in endpoints_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "HTTPException" in text and "429" in text:
            if not any(token in text for token in allowlist):
                violations.append(str(path.relative_to(root)))
    assert not violations, f"ad-hoc 429 in endpoints: {violations}"
