"""Production Google OAuth tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from urllib.parse import parse_qs, urlparse

from spark.api.v1.endpoints.auth import _username_base_from_email
from spark.core.config import settings
from spark.core.google_oauth import (
    OAuthStateError,
    email_allowed_for_oauth,
    normalize_google_profile,
    sign_oauth_state,
    verify_oauth_state,
)
from spark.core.oauth_exchange import consume_oauth_exchange_payload, store_oauth_exchange_payload
from spark.main import app


def test_oauth_state_roundtrip():
    state = sign_oauth_state()
    verify_oauth_state(state)


def test_oauth_state_preserves_from_path():
    state = sign_oauth_state("/documents?doc=abc")
    payload = verify_oauth_state(state)
    assert payload.get("from") == "/documents?doc=abc"


def test_oauth_state_preserves_web_origin():
    state = sign_oauth_state("/chat", web_origin="https://neospark.kcalsion.com/")
    payload = verify_oauth_state(state)
    assert payload.get("from") == "/chat"
    assert payload.get("web_origin") == "https://neospark.kcalsion.com"


def test_oauth_state_rejects_unsafe_from_path():
    state = sign_oauth_state("https://evil.com")
    payload = verify_oauth_state(state)
    assert "from" not in payload


def test_oauth_state_rejects_unsafe_web_origin():
    state = sign_oauth_state("/chat", web_origin="javascript:alert(1)")
    payload = verify_oauth_state(state)
    assert "web_origin" not in payload


def test_oauth_state_rejects_tamper():
    state = sign_oauth_state()
    body, sig = state.split(".", 1)
    bad = f"{body}x.{sig}"
    with pytest.raises(OAuthStateError):
        verify_oauth_state(bad)


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("alice@example.com", "alice"),
        ("Alice.Smith@corp.io", "alice_smith"),
        ("+++@example.com", "user"),
        ("very-long-local-part-that-exceeds-fifty-characters-limit@x.com", "very_long_local_part_that_exceeds_fifty_charac"),
    ],
)
def test_username_base_from_email(email: str, expected: str) -> None:
    assert _username_base_from_email(email) == expected


def test_normalize_google_profile_merges_sub_and_email() -> None:
    profile = normalize_google_profile(
        {
            "sub": "1234567890",
            "email": "alice@gmail.com",
            "name": "Alice",
            "picture": "https://example.com/a.jpg",
            "email_verified": True,
        }
    )
    assert profile["sub"] == "1234567890"
    assert profile["email"] == "alice@gmail.com"
    assert profile["name"] == "Alice"
    assert profile["picture"] == "https://example.com/a.jpg"
    assert profile["email_verified"] is True


def test_normalize_google_profile_rejects_string_false_verified() -> None:
    profile = normalize_google_profile({"email_verified": "false"})
    assert profile["email_verified"] is False


def test_email_allowed_for_oauth_with_domain_list(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_oauth_allowed_domains", "company.co.th,subsidiary.com")
    monkeypatch.setattr(settings, "app_env", "production")
    assert email_allowed_for_oauth("worker@company.co.th") is True
    assert email_allowed_for_oauth("worker@subsidiary.com") is True
    assert email_allowed_for_oauth("worker@gmail.com") is False


def test_email_allowed_production_empty_list_rejects(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_oauth_allowed_domains", "")
    monkeypatch.setattr(settings, "app_env", "production")
    assert email_allowed_for_oauth("worker@company.co.th") is False


def test_email_allowed_dev_empty_list_allows(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_oauth_allowed_domains", "")
    monkeypatch.setattr(settings, "app_env", "development")
    assert email_allowed_for_oauth("worker@gmail.com") is True


@pytest.mark.asyncio
async def test_oauth_exchange_code_roundtrip() -> None:
    payload = {
        "token": "tok",
        "token_type": "bearer",
        "expires_in": 3600,
        "username": "alice",
        "email": "alice@company.co.th",
        "full_name": "Alice",
        "picture_url": "",
        "factories": [],
    }
    code = await store_oauth_exchange_payload(payload)
    got = await consume_oauth_exchange_payload(code)
    assert got == payload
    assert await consume_oauth_exchange_payload(code) is None


def test_oauth_exchange_endpoint() -> None:
    client = TestClient(app)

    async def _store():
        return await store_oauth_exchange_payload(
            {
                "token": "jwt-test",
                "token_type": "bearer",
                "expires_in": 3600,
                "username": "bob",
                "email": "bob@company.co.th",
                "full_name": "Bob",
                "picture_url": "",
                "factories": [],
            }
        )

    import asyncio

    code = asyncio.run(_store())
    res = client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert res.status_code == 200
    body = res.json()
    assert body["token"] == "jwt-test"
    assert body["username"] == "bob"

    res2 = client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert res2.status_code == 401


def test_google_login_uses_public_web_callback_when_no_explicit_callback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "google-client")
    monkeypatch.setattr(settings, "google_client_secret", "google-secret")
    monkeypatch.setattr(settings, "google_oauth_callback_url", "")
    monkeypatch.setattr(settings, "web_app_url", "")

    client = TestClient(app)
    res = client.get(
        "/api/v1/auth/google/login?from=/chat",
        headers={
            "host": "neospark.kcalsion.com",
            "x-forwarded-proto": "https",
        },
        follow_redirects=False,
    )

    assert res.status_code == 302
    location = res.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert params["redirect_uri"] == [
        "https://neospark.kcalsion.com/api/v1/auth/google/callback"
    ]
    state_payload = verify_oauth_state(params["state"][0])
    assert state_payload["from"] == "/chat"
    assert state_payload["web_origin"] == "https://neospark.kcalsion.com"


def test_verify_google_id_token_rejects_bad_aud(monkeypatch) -> None:
    from spark.core.google_oauth import GoogleOAuthError, verify_google_id_token

    monkeypatch.setattr(settings, "google_client_id", "expected-client-id")

    with pytest.raises(GoogleOAuthError):
        verify_google_id_token("not.a.valid.jwt")
