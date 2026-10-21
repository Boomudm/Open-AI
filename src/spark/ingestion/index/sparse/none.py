"""No-op sparse encoder — dense + Postgres FTS only (Option C)."""

from __future__ import annotations

from qdrant_client.models import SparseVector


class NoneSparseEncoder:
    encoder_id = "none"

    def encode_document(self, text: str) -> SparseVector:
        del text
        return SparseVector(indices=[], values=[])

    def encode_query(self, text: str) -> SparseVector:
        del text
        return SparseVector(indices=[], values=[])

    def encode_documents(self, texts: list[str]) -> list[SparseVector]:
        return [self.encode_document(text) for text in texts]
