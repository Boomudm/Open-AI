"""Google OAuth 2.0 helpers (authorization code flow)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from spark.core.auth import _b64url, _b64url_decode, _secret
from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

OAUTH_STATE_TTL_SEC = 600
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


class OAuthStateError(Exception):
    pass


class GoogleOAuthError(Exception):
    pass


def google_oauth_configured() -> bool:
    return bool(settings.google_client_id.strip() and settings.google_client_secret.strip())


def email_allowed_for_oauth(email: str) -> bool:
    """Return True when email domain is permitted for Google OAuth."""
    domains = settings.google_oauth_allowed_domain_list
    if not domains:
        if settings.is_production:
            return False
        log.warning("oauth_domain_allowlist_empty_dev_bypass")
        return True

    parts = email.rsplit("@", 1)
    if len(parts) != 2 or not parts[0].strip():
        return False
    domain = parts[1].lower().strip()
    return domain in domains


def _validate_oauth_return_path(from_path: str | None) -> str | None:
    if not from_path or not from_path.strip():
        return None
    candidate = from_path.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return None
    lower = candidate.lower()
    if "javascript:" in lower or "data:" in lower:
        return None
    if len(candidate) > 2048:
        return None
    return candidate


def validate_oauth_web_origin(origin: str | None) -> str | None:
    if not origin or not origin.strip():
        return None
    candidate = origin.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc or parsed.username or parsed.password:
        return None
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def sign_oauth_state(from_path: str | None = None, *, web_origin: str | None = None) -> str:
    payload: dict[str, Any] = {
        "iat": int(time.time()),
        "exp": int(time.time()) + OAUTH_STATE_TTL_SEC,
    }
    validated_from = _validate_oauth_return_path(from_path)
    if validated_from:
        payload["from"] = validated_from
    validated_origin = validate_oauth_web_origin(web_origin)
    if validated_origin:
        payload["web_origin"] = validated_origin
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def verify_oauth_state(state: str) -> dict[str, Any]:
    try:
        body_b64, sig_b64 = state.split(".", 1)
    except ValueError as exc:
        raise OAuthStateError("invalid state") from exc

    expected = hmac.new(_secret(), body_b64.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        raise OAuthStateError("bad state signature")

    payload = json.loads(_b64url_decode(body_b64))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise OAuthStateError("state expired")
    return payload


GOOGLE_OAUTH_SCOPES = (
    "openid "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)


def verify_google_id_token(id_token_str: str) -> dict[str, Any]:
    """Verify Google id_token signature, audience, issuer, and expiry."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        raise GoogleOAuthError("invalid id_token") from exc

    issuer = claims.get("iss")
    if issuer not in GOOGLE_ISSUERS:
        raise GoogleOAuthError("invalid id_token issuer")
    return claims


def normalize_google_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Google userinfo / id_token fields to a stable profile dict."""
    sub = (raw.get("sub") or raw.get("id") or "").strip()
    email = (raw.get("email") or "").strip()
    name = (raw.get("name") or "").strip()
    picture = (raw.get("picture") or "").strip()
    email_verified = raw.get("email_verified")
    if isinstance(email_verified, str):
        email_verified = email_verified.lower() in {"true", "1", "yes"}
    return {
        "sub": sub,
        "email": email,
        "name": name or None,
        "picture": picture or None,
        "email_verified": email_verified,
    }


def build_google_authorize_url(*, state: str, redirect_uri: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def fetch_google_userinfo(code: str, redirect_uri: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_res.status_code >= 400:
            raise GoogleOAuthError(f"token exchange failed ({token_res.status_code})")

        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise GoogleOAuthError("missing access_token")

        profile: dict[str, Any] = {}
        id_token_value = token_data.get("id_token")
        if isinstance(id_token_value, str) and id_token_value.strip():
            verified = verify_google_id_token(id_token_value.strip())
            profile.update(verified)

        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code >= 400:
            raise GoogleOAuthError(f"userinfo failed ({user_res.status_code})")
        profile.update(user_res.json())
        return normalize_google_profile(profile)
