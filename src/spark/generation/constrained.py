"""Optional constrained decoding hook — post-hoc validation fallback (Phase 10)."""

from __future__ import annotations

CONSTRAINED_DECODING_AVAILABLE = False


def supports_constrained_citations() -> bool:
    """True when LLM backend exposes grammar/logits mask for citation tokens."""
    return CONSTRAINED_DECODING_AVAILABLE
