"""Phase 8 — frontend trust gate wired to operator actions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_operator_gate_module_and_component_exist() -> None:
    gate = ROOT / "web" / "lib" / "trust" / "operator-gate.ts"
    component = ROOT / "web" / "components" / "trust" / "OperatorTrustGate.tsx"
    from_message = ROOT / "web" / "lib" / "trust" / "from-message.ts"
    bubble = ROOT / "web" / "components" / "chat" / "gemini" / "ChatMessageBubble.tsx"

    gate_src = gate.read_text(encoding="utf-8")
    component_src = component.read_text(encoding="utf-8")
    from_message_src = from_message.read_text(encoding="utf-8")
    bubble_src = bubble.read_text(encoding="utf-8")

    assert "requiresOperatorGate" in gate_src
    assert "SAFETY_INTENTS" in gate_src
    assert "hasProvisionalTokens" in gate_src
    assert "requiresOperatorGate" in component_src
    assert "requiresOperatorGate" in from_message_src or "trustRequiresOperatorWarning" in from_message_src
    assert "OperatorTrustGate" in bubble_src


def test_trust_mapper_references_all_message_fields() -> None:
    from_message = ROOT / "web" / "lib" / "trust" / "from-message.ts"
    chat_msg = ROOT / "web" / "lib" / "chat.ts"
    types_src = ROOT / "web" / "lib" / "trust" / "types.ts"

    from_message_text = from_message.read_text(encoding="utf-8")
    chat_msg_text = chat_msg.read_text(encoding="utf-8")
    types_text = types_src.read_text(encoding="utf-8")

    for field in (
        "confidence_tier",
        "citations_verified",
        "retrieval_report",
        "system_degradation",
        "cache_hit",
    ):
        assert field in chat_msg_text, f"ChatMsg missing {field}"
        assert field in from_message_text, f"from-message.ts must map {field}"

    assert "OperatorTrustState" in types_text
    assert "operatorTrustFromMessage" in from_message_text
    assert "operatorTrustFromStreamParts" in from_message_text
