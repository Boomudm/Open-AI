"""Ingest upload dedup and validation edge cases."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from spark.core.config import settings
from spark.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "auth_required", False)
    return TestClient(app)


def test_ingest_same_hash_requeues_instead_of_500(client: TestClient) -> None:
    tag = uuid.uuid4().hex[:8]
    payload = f"%PDF-1.4\n% dedup test {tag}\n".encode()
    files = {"file": (f"dedup-{tag}.pdf", payload, "application/pdf")}

    first = client.post(
        "/api/v1/ingest/file",
        data={"factory_id": "F-01", "document_type": "knowledge_document", "title": "first"},
        files=files,
    )
    assert first.status_code == 202, first.text
    first_doc = first.json()["doc_id"]

    second = client.post(
        "/api/v1/ingest/file",
        data={"factory_id": "F-01", "document_type": "iso_certificate", "title": "second"},
        files=files,
    )
    assert second.status_code == 202, second.text
    assert second.json()["doc_id"] == first_doc


def test_ingest_machine_manual_accepts_missing_machine(client: TestClient) -> None:
    """machine_id is optional (product decision 2026-07) — forcing a machine
    pick at upload 400'd the primary flow; employees can scope later."""
    res = client.post(
        "/api/v1/ingest/file",
        data={"factory_id": "F-01", "document_type": "machine_manual"},
        files={"file": ("manual.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 202, res.text
