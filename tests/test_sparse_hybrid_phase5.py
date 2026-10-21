"""Phase 5 — no hash-bucket sparse encoder remains."""

from __future__ import annotations

from pathlib import Path


def test_hash_sparse_encoder_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/spark/ingestion/index/sparse_encoder.py").exists()
    assert not (root / "src/spark/ingestion/sparse_encoder.py").exists()


def test_sparse_encoder_id_in_payload_contract() -> None:
    from spark.contracts.rag_payload_contract import QDRANT_PAYLOAD_FIELDS

    assert "sparse_encoder_id" in QDRANT_PAYLOAD_FIELDS


def test_production_lock_requires_bge_m3_sparse() -> None:
    from spark.core.production_lock import load_production_lock_manifest

    manifest = load_production_lock_manifest()
    assert manifest.required["sparse_encoder"] == "bge_m3"
    assert manifest.enforcement.get("sparse_encoder") is True
