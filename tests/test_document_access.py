"""Document library access rules (factory + job-position ACL)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from spark.core.security import Principal, enforce_factory_access
from spark.services.document_access_service import (
    _passes_factory_acl,
    passes_job_position_acl,
)


class _FakeDoc:
    def __init__(self, factory_id: str | None) -> None:
        self.factory_id = factory_id
        self.doc_id = uuid.uuid4()


def test_admin_passes_factory_acl() -> None:
    admin = Principal(user_id="1", username="admin", roles=("admin",), factory_access={})
    assert _passes_factory_acl(admin, _FakeDoc("F-02")) is True


def test_factory_grant() -> None:
    viewer = Principal(
        user_id="2",
        username="viewer_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    assert _passes_factory_acl(viewer, _FakeDoc("F-01")) is True
    assert _passes_factory_acl(viewer, _FakeDoc("F-02")) is False


def test_global_doc_requires_grant() -> None:
    viewer = Principal(
        user_id="2",
        username="viewer_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    assert _passes_factory_acl(viewer, _FakeDoc(None)) is True

    no_grant = Principal(user_id="3", username="none", roles=("employee",), factory_access={})
    assert _passes_factory_acl(no_grant, _FakeDoc(None)) is False


def test_enforce_factory_access_operator() -> None:
    operator = Principal(
        user_id=str(uuid.uuid4()),
        username="operator_f01",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )
    enforce_factory_access(operator, "F-01", "read")
    with pytest.raises(HTTPException) as exc:
        enforce_factory_access(operator, "F-02", "read")
    assert exc.value.status_code == 403


def test_position_acl_empty_user_positions() -> None:
    user = Principal(
        user_id="u",
        username="u",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
    )
    assert passes_job_position_acl(user, {uuid.uuid4()}) is False
