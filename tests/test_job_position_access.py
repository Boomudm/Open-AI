"""Tests for job-position document ACL and ingest scope validation."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.security import Principal
from spark.main import app
from spark.services.document_access_service import (
    passes_job_position_acl,
    _passes_factory_acl,
)


class _FakeDoc:
    def __init__(self, factory_id: str | None, doc_id: uuid.UUID | None = None) -> None:
        self.factory_id = factory_id
        self.doc_id = doc_id or uuid.uuid4()


def test_passes_job_position_acl_unrestricted() -> None:
    principal = Principal(
        user_id="u1",
        username="u1",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
    )
    assert passes_job_position_acl(principal, None) is True


def test_passes_job_position_acl_requires_match() -> None:
    pid = uuid.uuid4()
    principal = Principal(
        user_id="u1",
        username="u1",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(str(pid),),
    )
    assert passes_job_position_acl(principal, {pid}) is True
    assert passes_job_position_acl(principal, {uuid.uuid4()}) is False


def test_passes_factory_acl() -> None:
    viewer = Principal(
        user_id="2",
        username="viewer_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    assert _passes_factory_acl(viewer, _FakeDoc("F-01")) is True
    assert _passes_factory_acl(viewer, _FakeDoc("F-02")) is False


def _employee_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "username": "operator_f01",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "job_position_ids": [],
            "token_version": 0,
        }
    )


def test_ingest_requires_factory_id(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", False)
    client = TestClient(app)
    res = client.post(
        "/api/v1/ingest/file",
        data={"document_type": "machine_manual"},
        files={"file": ("manual.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 422


def test_ingest_unknown_machine_id(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", False)
    client = TestClient(app)
    res = client.post(
        "/api/v1/ingest/file",
        data={"machine_id": "NO-SUCH-MACHINE", "document_type": "machine_manual"},
        files={"file": ("manual.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 422
    assert "unknown machine_id" in res.json()["detail"]


def test_ingest_denied_for_other_factory(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    token = _employee_token()
    client = TestClient(app)
    res = client.post(
        "/api/v1/ingest/file",
        headers={"Authorization": f"Bearer {token}"},
        data={"factory_id": "F-02", "document_type": "machine_manual"},
        files={"file": ("manual.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 403


def test_ingest_denied_for_read_only_employee_on_own_factory(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    token = _employee_token()
    client = TestClient(app)
    res = client.post(
        "/api/v1/ingest/file",
        headers={"Authorization": f"Bearer {token}"},
        data={"factory_id": "F-01", "document_type": "machine_manual"},
        files={"file": ("manual.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert res.status_code == 403
