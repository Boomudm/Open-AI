"""Lite readiness probe tier (app-layer v2 Phase 11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.readyz_probe import clear_readyz_cache_for_tests
from spark.main import app


@pytest.fixture(autouse=True)
def _clear_readyz_cache() -> None:
    clear_readyz_cache_for_tests()


@pytest.mark.asyncio
async def test_readyz_lite_only_postgres_and_redis() -> None:
    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.execute = AsyncMock()

    with patch(
        "spark.core.readyz_probe.Cache.get",
        return_value=type("C", (), {"ping": AsyncMock(return_value=True)})(),
    ), patch(
        "spark.core.readyz_probe.AsyncSessionLocal",
        return_value=fake_session,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/readyz", params={"lite": "1"})

    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "lite"
    assert set(body["checks"].keys()) == {"postgres", "redis"}
    assert body["checks"]["postgres"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


@pytest.mark.asyncio
async def test_readyz_full_uses_cache_without_deep() -> None:
    from spark.core.readyz_probe import clear_readyz_cache_for_tests, readyz_full

    clear_readyz_cache_for_tests()
    with patch(
        "spark.workers.celery_app.check_celery_worker_health",
        return_value={"ok": True, "workers": 1, "worker_names": ["celery@test"]},
    ) as celery_mock, patch(
        "spark.storage.check_storage_health",
        return_value={"ok": True, "backend": "local", "path": "/tmp/docs"},
    ):
        await readyz_full(bypass_cache=False)
        await readyz_full(bypass_cache=False)

    assert celery_mock.call_count == 1


@pytest.mark.asyncio
async def test_readyz_deep_bypasses_cache() -> None:
    clear_readyz_cache_for_tests()

    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.execute = AsyncMock()

    fake_cache = type("C", (), {"ping": AsyncMock(return_value=True)})()

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
    ) as mock_httpx:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client_inst = AsyncMock()
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        mock_client_inst.get = AsyncMock(return_value=mock_resp)
        mock_httpx.return_value = mock_client_inst

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/readyz", params={"deep": "1"})
            second = await client.get("/readyz", params={"deep": "1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json().get("tier") == "full"
    assert "celery" in first.json()["checks"]
