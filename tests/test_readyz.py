"""Readiness endpoint checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.readyz_probe import clear_readyz_cache_for_tests
from spark.main import app


@pytest.fixture(autouse=True)
def _clear_readyz_cache() -> None:
    clear_readyz_cache_for_tests()


def _readyz_deep_mocks():
    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.execute = AsyncMock()
    fake_cache = type("C", (), {"ping": AsyncMock(return_value=True)})()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_client_inst = AsyncMock()
    mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
    mock_client_inst.__aexit__ = AsyncMock(return_value=False)
    mock_client_inst.get = AsyncMock(return_value=mock_resp)
    return fake_session, fake_cache, mock_client_inst


@pytest.mark.asyncio
async def test_readyz_includes_celery_check_with_http_200() -> None:
    fake_session, fake_cache, mock_client_inst = _readyz_deep_mocks()
    with patch(
        "spark.workers.celery_app.check_celery_worker_health",
        return_value={"ok": True, "workers": 1, "worker_names": ["celery@test"]},
    ), patch(
        "spark.storage.check_storage_health",
        return_value={"ok": True, "backend": "local", "path": "/tmp/docs"},
    ), patch(
        "spark.core.readyz_probe.AsyncSessionLocal",
        return_value=fake_session,
    ), patch(
        "spark.core.readyz_probe.Cache.get",
        return_value=fake_cache,
    ), patch(
        "spark.core.readyz_probe.httpx.AsyncClient",
        return_value=mock_client_inst,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz", params={"deep": "1"})

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["celery"]["ok"] is True
    assert body["checks"]["celery"]["workers"] == 1


@pytest.mark.asyncio
async def test_readyz_includes_storage_check() -> None:
    fake_session, fake_cache, mock_client_inst = _readyz_deep_mocks()
    with patch(
        "spark.workers.celery_app.check_celery_worker_health",
        return_value={"ok": True, "workers": 1, "worker_names": ["celery@test"]},
    ), patch(
        "spark.storage.check_storage_health",
        return_value={"ok": True, "backend": "local", "path": "/tmp/docs"},
    ), patch(
        "spark.core.readyz_probe.AsyncSessionLocal",
        return_value=fake_session,
    ), patch(
        "spark.core.readyz_probe.Cache.get",
        return_value=fake_cache,
    ), patch(
        "spark.core.readyz_probe.httpx.AsyncClient",
        return_value=mock_client_inst,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz", params={"deep": "1"})

    assert response.status_code == 200
    assert response.json()["checks"]["storage"]["ok"] is True


@pytest.mark.asyncio
async def test_readyz_celery_unavailable_returns_503() -> None:
    fake_session, fake_cache, mock_client_inst = _readyz_deep_mocks()
    with patch(
        "spark.workers.celery_app.check_celery_worker_health",
        return_value={"ok": False, "status": "unavailable"},
    ), patch(
        "spark.storage.check_storage_health",
        return_value={"ok": True, "backend": "local", "path": "/tmp/docs"},
    ), patch(
        "spark.core.readyz_probe.AsyncSessionLocal",
        return_value=fake_session,
    ), patch(
        "spark.core.readyz_probe.Cache.get",
        return_value=fake_cache,
    ), patch(
        "spark.core.readyz_probe.httpx.AsyncClient",
        return_value=mock_client_inst,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz", params={"deep": "1"})

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["celery"] == {"ok": False, "status": "unavailable"}
