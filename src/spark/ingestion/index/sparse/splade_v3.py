"""SPLADE-v3 sparse encoder stub — not enabled in Phase 5 default profile."""

from __future__ import annotations

from qdrant_client.models import SparseVector


class SpladeV3SparseEncoder:
    encoder_id = "splade_v3"

    def encode_document(self, text: str) -> SparseVector:
        del text
        raise NotImplementedError("splade_v3 sparse encoder is not wired in Phase 5")

    def encode_query(self, text: str) -> SparseVector:
        del text
        raise NotImplementedError("splade_v3 sparse encoder is not wired in Phase 5")
