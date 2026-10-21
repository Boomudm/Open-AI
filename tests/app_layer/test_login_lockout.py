"""Login brute-force lockout (app-layer Phase 2)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from spark.services.auth_login_guard import (
    assert_login_allowed,
    clear_login_failures,
    record_login_failure,
)


def _login_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.10", 50000),
            "server": ("testserver", 80),
        }
    )


@pytest.fixture
def login_guard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spark.services.auth_login_guard._login_limits",
        lambda: (5, 900, 900),
    )


@pytest.mark.asyncio
async def test_sixth_failed_login_returns_429(login_guard_enabled: None) -> None:
    request = _login_request()
    username = "employee_f01"

    for _ in range(5):
        await record_login_failure(request, username=username)

    with pytest.raises(HTTPException) as exc:
        await assert_login_allowed(request, username=username)

    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") is not None
    detail = exc.value.detail
    if isinstance(detail, dict):
        assert detail.get("code") == "login_rate_limited"
    else:
        assert "login_rate_limited" in str(detail)


@pytest.mark.asyncio
async def test_successful_login_clears_lockout(login_guard_enabled: None) -> None:
    request = _login_request()
    username = "employee_f01"

    for _ in range(5):
        await record_login_failure(request, username=username)

    with pytest.raises(HTTPException):
        await assert_login_allowed(request, username=username)

    await clear_login_failures(request, username=username)
    await assert_login_allowed(request, username=username)
