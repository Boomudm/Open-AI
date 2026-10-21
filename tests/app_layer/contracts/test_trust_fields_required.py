"""Phase 12 — AskResponse + SSE done must expose trust fields consumed by the UI."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ASK_RESPONSE_TRUST_FIELDS = (
    "confidence_tier",
    "citations_verified",
    "retrieval_report",
    "system_degradation",
    "cache_hit",
)

SSE_DONE_TRUST_FIELDS = (
    "assistant_message_id",
    "cache_hit",
    "confidence_tier",
    "citations_verified",
)


def test_ask_response_type_lists_trust_fields() -> None:
    types_src = (ROOT / "web" / "lib" / "api" / "types.ts").read_text(encoding="utf-8")
    assert "export type AskResponse" in types_src
    for field in ASK_RESPONSE_TRUST_FIELDS:
        assert field in types_src, f"AskResponse missing {field}"


def test_sse_done_payload_lists_trust_fields() -> None:
    sse_types = (ROOT / "web" / "lib" / "chat" / "sse-types.ts").read_text(encoding="utf-8")
    assert "export type ChatSseDonePayload" in sse_types
    for field in SSE_DONE_TRUST_FIELDS:
        assert field in sse_types, f"ChatSseDonePayload missing {field}"


def test_openapi_chat_ask_documents_trust_fields() -> None:
    """FastAPI OpenAPI schema includes core trust fields on chat ask responses."""
    from spark.main import app

    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    ask_schema = None
    for name, body in components.items():
        if "Ask" in name and isinstance(body, dict) and "properties" in body:
            props = body.get("properties") or {}
            if "answer" in props and "confidence_tier" in props:
                ask_schema = props
                break
    assert ask_schema is not None, "AskResponse schema not found in OpenAPI"
    for field in ("confidence_tier", "cache_hit"):
        assert field in ask_schema, f"OpenAPI AskResponse missing {field}"
