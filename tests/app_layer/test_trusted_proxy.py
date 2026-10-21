"""Trusted proxy client IP resolution (app-layer v2 Phase 1)."""

from __future__ import annotations

from starlette.requests import Request

from spark.api.platform.trusted_proxy import client_ip


def _request(
    *,
    peer: str = "10.0.0.1",
    xff: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345),
    }
    return Request(scope)


def test_ignores_xff_without_trusted_peer(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "trusted_proxies", "172.16.0.0/12")
    req = _request(peer="203.0.113.50", xff="1.2.3.4, 10.0.0.1")
    assert client_ip(req) == "203.0.113.50"


def test_honors_xff_from_trusted_peer(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.0/8")
    req = _request(peer="10.0.0.5", xff="1.2.3.4, 10.0.0.5")
    assert client_ip(req) == "1.2.3.4"
