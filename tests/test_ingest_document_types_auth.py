"""Ingest document-types requires authentication."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.config import settings
from spark.main import app


@pytest.mark.asyncio
async def test_ingest_document_types_requires_auth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "auth_required", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/ingest/document-types")
    assert res.status_code == 401
