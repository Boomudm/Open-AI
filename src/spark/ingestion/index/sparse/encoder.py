"""Sparse encoder protocol and factory."""

from __future__ import annotations

from typing import Literal, Protocol

from qdrant_client.models import SparseVector

from spark.core.production_profile import ProductionProfile

SparseEncoderKind = Literal["bge_m3", "splade_v3", "none"]


class SparseEncoder(Protocol):
    @property
    def encoder_id(self) -> str: ...

    def encode_document(self, text: str) -> SparseVector: ...

    def encode_query(self, text: str) -> SparseVector: ...


class SparseEncoderFactory:
    @staticmethod
    def create(kind: SparseEncoderKind) -> SparseEncoder:
        if kind == "none":
            from spark.ingestion.index.sparse.none import NoneSparseEncoder

            return NoneSparseEncoder()
        if kind == "splade_v3":
            from spark.ingestion.index.sparse.splade_v3 import SpladeV3SparseEncoder

            return SpladeV3SparseEncoder()
        from spark.ingestion.index.sparse.bge_m3_sparse import BgeM3SparseEncoder

        return BgeM3SparseEncoder()

    @staticmethod
    def from_settings() -> SparseEncoder:
        profile = ProductionProfile.from_settings()
        if not profile.sparse_vectors_enabled:
            return SparseEncoderFactory.create("none")
        return SparseEncoderFactory.create(profile.sparse_encoder)


def get_sparse_encoder() -> SparseEncoder:
    return SparseEncoderFactory.from_settings()
