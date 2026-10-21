"""HMAC-signed eval tokens tied to eval report hashes (Phase 13)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def eval_token_secret() -> bytes:
    raw = os.environ.get("EVAL_TOKEN_HMAC_SECRET") or os.environ.get("SPARK_EVAL_TOKEN_SECRET") or ""
    if not raw.strip():
        raise ValueError("EVAL_TOKEN_HMAC_SECRET is required to sign or verify eval tokens")
    return raw.encode("utf-8")


def hash_report_dir(report_dir: Path, *, suite_names: list[str]) -> str:
    digest = hashlib.sha256()
    for suite in sorted(suite_names):
        path = report_dir / f"{suite}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Missing eval report: {path}")
        digest.update(suite.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def sign_eval_payload(payload: dict[str, Any], *, secret: bytes | None = None) -> dict[str, Any]:
    key = secret or eval_token_secret()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return {"payload": payload, "signature": signature}


def verify_eval_payload(signed: dict[str, Any], *, secret: bytes | None = None) -> dict[str, Any]:
    key = secret or eval_token_secret()
    payload = signed.get("payload")
    signature = signed.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise ValueError("invalid eval token structure")
    expected = sign_eval_payload(payload, secret=key)["signature"]
    if not hmac.compare_digest(expected, signature):
        raise ValueError("eval token signature mismatch")
    expires_at = payload.get("expires_at")
    if expires_at:
        expiry = datetime.fromisoformat(str(expires_at))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if datetime.now(tz=UTC) >= expiry:
            raise ValueError("eval token expired")
    return payload
