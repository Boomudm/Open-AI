"""Phase 12 — dual admission plane contract."""

from __future__ import annotations

from spark.api.platform.route_policy import resolve_route_policy


def test_health_exempt_from_concurrency() -> None:
    policy = resolve_route_policy("GET", "/healthz")
    assert policy.admission_plane == "exempt"
    assert policy.concurrency_exempt is True


def test_chat_stream_uses_sse_plane() -> None:
    policy = resolve_route_policy("GET", "/api/v1/ingest/jobs/{id}/stream")
    assert policy.admission_plane == "sse"
    assert policy.concurrency_exempt is False


def test_chat_stream_ask_has_transactional_default_with_sse_upgrade() -> None:
    policy = resolve_route_policy("POST", "/api/v1/chat/{session_id}/ask")
    assert policy.admission_plane == "transactional"
    from spark.api.platform.middleware.admission import _body_indicates_stream

    assert _body_indicates_stream(b'{"question":"q","stream":true}')


def test_transactional_post_uses_transactional_plane() -> None:
    policy = resolve_route_policy("POST", "/api/v1/feedback")
    assert policy.admission_plane == "transactional"
