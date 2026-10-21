"""First-login job position onboarding."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from spark.core.auth import issue_token
from spark.core.security import Principal, can_write_factory
from spark.main import app


def test_can_write_factory_operator_role() -> None:
    operator = Principal(
        user_id="u1",
        username="op",
        roles=("operator",),
        factory_access={"F-01": "read"},
    )
    assert can_write_factory(operator, "F-01") is True


def test_set_my_job_position_rejects_repeat() -> None:
    token = issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "emp2",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "job_position_ids": [str(uuid.uuid4())],
            "token_version": 0,
        }
    )
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/job-position",
        headers={"Authorization": f"Bearer {token}"},
        json={"position_id": str(uuid.uuid4())},
    )
    assert res.status_code == 409


def test_set_my_job_position_rejects_admin() -> None:
    token = issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "admin",
            "roles": ["admin"],
            "factory_access": {},
            "job_position_ids": [],
            "token_version": 0,
        }
    )
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/job-position",
        headers={"Authorization": f"Bearer {token}"},
        json={"position_id": str(uuid.uuid4())},
    )
    assert res.status_code == 400
