"""Phase 13 — HMAC eval token signature and report hash binding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spark.ingestion.eval_gate import _validate_cached_token, fetch_eval_token
from spark.ingestion.eval_token import (
    hash_report_dir,
    sign_eval_payload,
    verify_eval_payload,
)


@pytest.fixture
def hmac_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TOKEN_HMAC_SECRET", "test-eval-hmac-secret")


def test_sign_and_verify_round_trip(hmac_secret: None) -> None:
    payload = {
        "report_sha256": "abc123",
        "lock_version": 3,
        "config_hash": "deadbeef",
        "expires_at": (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat(),
    }
    signed = sign_eval_payload(payload)
    verified = verify_eval_payload(signed)
    assert verified["report_sha256"] == "abc123"


def test_verify_rejects_tampered_signature(hmac_secret: None) -> None:
    signed = sign_eval_payload({"report_sha256": "x", "lock_version": 3})
    signed = dict(signed)
    signed["signature"] = "0" * 64
    with pytest.raises(ValueError, match="signature mismatch"):
        verify_eval_payload(signed)


def test_verify_rejects_expired_token(hmac_secret: None) -> None:
    payload = {
        "report_sha256": "abc",
        "expires_at": (datetime.now(tz=UTC) - timedelta(seconds=1)).isoformat(),
    }
    signed = sign_eval_payload(payload)
    with pytest.raises(ValueError, match="expired"):
        verify_eval_payload(signed)


def test_hash_report_dir_is_stable(tmp_path: Path) -> None:
    for suite in ("baseline_ci", "heldout"):
        (tmp_path / f"{suite}.json").write_text('{"metrics": {}}', encoding="utf-8")
    first = hash_report_dir(tmp_path, suite_names=["baseline_ci", "heldout"])
    second = hash_report_dir(tmp_path, suite_names=["heldout", "baseline_ci"])
    assert first == second


def test_validate_cached_token_rejects_legacy_unsigned(hmac_secret: None) -> None:
    legacy = {
        "config_hash": "abc",
        "expires_at": (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat(),
    }
    assert _validate_cached_token(legacy) is None


def test_validate_cached_token_rejects_unsigned_with_report_hash(hmac_secret: None) -> None:
    unsigned = {
        "report_sha256": "abc123",
        "expires_at": (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat(),
    }
    assert _validate_cached_token(unsigned) is None


def test_validate_cached_token_accepts_signed_payload(hmac_secret: None) -> None:
    payload = {
        "report_sha256": "abc123",
        "lock_version": 3,
        "expires_at": (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat(),
    }
    signed = sign_eval_payload(payload)
    validated = _validate_cached_token(signed)
    assert validated is not None
    assert validated["report_sha256"] == "abc123"


@pytest.mark.asyncio
async def test_fetch_eval_token_rejects_legacy_cache(monkeypatch: pytest.MonkeyPatch, hmac_secret: None) -> None:
    legacy = {
        "report_sha256": "legacy",
        "expires_at": (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat(),
    }

    class _Cache:
        async def get_json(self, _key: str) -> dict | None:
            return legacy

    monkeypatch.setattr("spark.core.cache.Cache.get", lambda: _Cache())
    token = await fetch_eval_token("F-01", "config-hash")
    assert token is None
