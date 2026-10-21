"""JWT-based authentication primitives for P3 RBAC.

Tokens are signed with HS256 using `JWT_SECRET`. For non-production demos we
can accept unauthenticated requests as the `system` principal; production
(`APP_ENV=production`) always makes `Bearer ...` mandatory.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from spark.core.config import INSECURE_JWT_SECRETS, settings

ALG = "HS256"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _secret() -> bytes:
    secret = (getattr(settings, "jwt_secret", "") or "").strip()
    if not secret or secret in INSECURE_JWT_SECRETS:
        if settings.is_production:
            raise RuntimeError(
                "JWT_SECRET must be set to a strong, non-default value when APP_ENV=production"
            )
        secret = "dev-secret-change-me"
    return secret.encode("utf-8")


def issue_token(claims: dict[str, Any], ttl_seconds: int = 8 * 3600) -> str:
    header = {"alg": ALG, "typ": "JWT"}
    now = int(time.time())
    body = {**claims, "iat": now, "exp": now + ttl_seconds}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    body_b64 = _b64url(json.dumps(body, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{body_b64}".encode()
    sig = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{body_b64}.{_b64url(sig)}"


class TokenError(Exception):
    pass


def verify_token(token: str) -> dict[str, Any]:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("invalid token format") from exc

    signing_input = f"{header_b64}.{body_b64}".encode()
    expected_sig = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        raise TokenError("bad signature")

    body = json.loads(_b64url_decode(body_b64))
    if int(body.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")
    return body


def hash_password(plain: str) -> str:
    """Argon2id with per-user salt (production). Legacy pbkdf2 hashes still verify."""
    from argon2 import PasswordHasher

    ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
    return f"argon2${ph.hash(plain)}"


def _verify_pbkdf2(plain: str, hashed: str) -> bool:
    try:
        scheme, iters, salt, encoded = hashed.split("$")
        if scheme != "pbkdf2":
            return False
        derived = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), int(iters))
        return hmac.compare_digest(base64.b64decode(encoded), derived)
    except Exception:
        return False


def _verify_argon2(plain: str, hashed: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    try:
        _, digest = hashed.split("$", 1)
        PasswordHasher().verify(digest, plain)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("argon2$"):
        return _verify_argon2(plain, hashed)
    if hashed.startswith("pbkdf2$"):
        return _verify_pbkdf2(plain, hashed)
    # Legacy demo format without prefix
    salt = base64.b64encode(b"spark-static-salt").decode()
    legacy = f"pbkdf2$120000${salt}${hashed}" if "$" not in hashed else hashed
    return _verify_pbkdf2(plain, legacy) if legacy.startswith("pbkdf2$") else False


def generate_password_salt() -> str:
    return secrets.token_urlsafe(16)
