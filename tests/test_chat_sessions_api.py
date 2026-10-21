"""Chat session list, patch pin/rename, auto-title, and per-user isolation."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.org import User
from spark.main import app


@pytest.fixture(autouse=True)
def _demo_auth_for_session_tests(monkeypatch) -> None:
    """Most chat session tests assume demo mode; isolation test sets auth_required=True."""
    monkeypatch.setattr(settings, "auth_required", False)


def _user_token(sub: str, username: str) -> str:
    return issue_token(
        {
            "sub": sub,
            "username": username,
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
        }
    )


@pytest.mark.asyncio
async def test_create_session_null_title() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/chat/sessions", json={})
        assert res.status_code == 201
        body = res.json()
        assert body["title"] is None
        assert body["pinned"] is False


@pytest.mark.asyncio
async def test_patch_pin_and_rename() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/chat/sessions", json={})
        session_id = created.json()["session_id"]

        renamed = await client.patch(
            f"/api/v1/chat/sessions/{session_id}",
            json={"title": "ทดสอบชื่อแชท"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "ทดสอบชื่อแชท"

        pinned = await client.patch(
            f"/api/v1/chat/sessions/{session_id}",
            json={"pinned": True},
        )
        assert pinned.status_code == 200
        assert pinned.json()["pinned"] is True


@pytest.mark.asyncio
async def test_list_sessions_pinned_first(monkeypatch, isolated_chat_user) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        a = (
            await client.post(
                "/api/v1/chat/sessions", json={"title": "A"}, headers=isolated_chat_user
            )
        ).json()
        b = (
            await client.post(
                "/api/v1/chat/sessions", json={"title": "B"}, headers=isolated_chat_user
            )
        ).json()
        await client.patch(
            f"/api/v1/chat/sessions/{b['session_id']}",
            json={"pinned": True},
            headers=isolated_chat_user,
        )

        listed = await client.get(
            "/api/v1/chat/sessions?page=1&page_size=50", headers=isolated_chat_user
        )
        assert listed.status_code == 200
        items = listed.json()["items"]
        ids = [i["session_id"] for i in items]
        assert ids.index(b["session_id"]) < ids.index(a["session_id"])
        assert all("message_count" in i for i in items)


@pytest.mark.asyncio
async def test_list_sessions_sidebar_hides_empty_default(
    monkeypatch, isolated_chat_user
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        empty = (
            await client.post(
                "/api/v1/chat/sessions", json={}, headers=isolated_chat_user
            )
        ).json()
        named = (
            await client.post(
                "/api/v1/chat/sessions",
                json={"title": "มีชื่อ"},
                headers=isolated_chat_user,
            )
        ).json()

        sidebar = await client.get(
            "/api/v1/chat/sessions?for_sidebar=true&page=1&page_size=50",
            headers=isolated_chat_user,
        )
        assert sidebar.status_code == 200
        ids = {i["session_id"] for i in sidebar.json()["items"]}
        assert named["session_id"] in ids
        assert empty["session_id"] not in ids

        included = await client.get(
            f"/api/v1/chat/sessions?for_sidebar=true&include_session_id={empty['session_id']}",
            headers=isolated_chat_user,
        )
        assert empty["session_id"] in {i["session_id"] for i in included.json()["items"]}


@pytest.fixture
async def isolated_chat_user() -> dict[str, str]:
    """Unique user so session list tests are not polluted by shared demo sessions."""
    uid = uuid.uuid4()
    username = f"session_test_{uid.hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(
            User(
                user_id=uid,
                username=username,
                email=f"{username}@spark.test",
                is_active=True,
            )
        )
        await db.commit()
    token = issue_token(
        {
            "sub": str(uid),
            "username": username,
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def chat_test_users() -> None:
    uid_a = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    uid_b = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
    async with AsyncSessionLocal() as db:
        for uid, name in ((uid_a, "alice_chat"), (uid_b, "bob_chat")):
            if await db.get(User, uid) is None:
                db.add(
                    User(
                        user_id=uid,
                        username=name,
                        email=f"{name}@spark.test",
                        is_active=True,
                    )
                )
        await db.commit()


@pytest.mark.asyncio
async def test_sessions_isolated_per_user(monkeypatch, chat_test_users) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    transport = ASGITransport(app=app)
    user_a = _user_token("00000000-0000-0000-0000-0000000000a1", "alice")
    user_b = _user_token("00000000-0000-0000-0000-0000000000b2", "bob")
    headers_a = {"Authorization": f"Bearer {user_a}"}
    headers_b = {"Authorization": f"Bearer {user_b}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/chat/sessions", json={"title": "Alice chat"}, headers=headers_a)
        assert created.status_code == 201
        alice_id = created.json()["session_id"]

        listed_b = await client.get("/api/v1/chat/sessions?page=1&page_size=50", headers=headers_b)
        assert listed_b.status_code == 200
        assert alice_id not in {i["session_id"] for i in listed_b.json()["items"]}

        forbidden = await client.get(f"/api/v1/chat/{alice_id}/messages", headers=headers_b)
        assert forbidden.status_code == 404

        patch_b = await client.patch(
            f"/api/v1/chat/sessions/{alice_id}",
            json={"title": "hijack"},
            headers=headers_b,
        )
        assert patch_b.status_code == 404

    monkeypatch.setattr(settings, "auth_required", False)


