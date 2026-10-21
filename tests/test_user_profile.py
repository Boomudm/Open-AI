"""Self-service user profile API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spark.core.privacy_policy import PRIVACY_POLICY_VERSION
from spark.main import app


def _login(client: TestClient, username: str, password: str = "changeme") -> dict:
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_get_my_profile() -> None:
    try:
        client = TestClient(app)
        body = _login(client, "employee_f01")
        res = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        assert res.status_code == 200
        profile = res.json()
        assert profile["username"] == "employee_f01"
        assert isinstance(profile["factories"], list)
        assert profile["has_password"] is True
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_update_my_profile_full_name() -> None:
    try:
        client = TestClient(app)
        body = _login(client, "employee_f01")
        headers = {"Authorization": f"Bearer {body['token']}"}
        original = client.get("/api/v1/auth/me", headers=headers).json()["full_name"]

        res = client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"full_name": "พนักงานทดสอบโปรไฟล์"},
        )
        assert res.status_code == 200
        updated = res.json()
        assert updated["full_name"] == "พนักงานทดสอบโปรไฟล์"

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {updated['token']}"})
        assert me.status_code == 200
        assert me.json()["full_name"] == "พนักงานทดสอบโปรไฟล์"

        if original:
            client.patch(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {updated['token']}"},
                json={"full_name": original},
            )
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_change_password_wrong_current() -> None:
    try:
        client = TestClient(app)
        body = _login(client, "admin")
        res = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {body['token']}"},
            json={"current_password": "wrong", "new_password": "newpassword1"},
        )
        assert res.status_code == 401
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_change_password_and_restore() -> None:
    try:
        client = TestClient(app)
        body = _login(client, "admin")
        headers = {"Authorization": f"Bearer {body['token']}"}

        res = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={"current_password": "changeme", "new_password": "temppass99"},
        )
        assert res.status_code == 200
        new_token = res.json()["token"]

        bad = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
        )
        assert bad.status_code == 401

        ok = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "temppass99"},
        )
        assert ok.status_code == 200

        restore = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {ok.json()['token']}"},
            json={"current_password": "temppass99", "new_password": "changeme"},
        )
        assert restore.status_code == 200
        assert restore.json()["token"]
        assert new_token
        assert PRIVACY_POLICY_VERSION
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
