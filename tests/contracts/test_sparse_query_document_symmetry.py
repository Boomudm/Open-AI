"""Sparse encoding symmetry — index and retrieval share get_sparse_encoder()."""

from __future__ import annotations

from qdrant_client.models import SparseVector

from spark.contracts.sparse_encoding_contract import index_sparse_encoder, retrieval_sparse_encoder


def test_index_and_retrieval_use_same_sparse_factory() -> None:
    index_enc = index_sparse_encoder()
    retrieval_enc = retrieval_sparse_encoder()
    assert type(index_enc) is type(retrieval_enc)
    assert index_enc.encoder_id == retrieval_enc.encoder_id


def test_sparse_query_document_symmetry() -> None:
    encoder = index_sparse_encoder()
    text = "Servo motor MC-001 overheating limit 80C"
    doc_vec = encoder.encode_document(text)
    query_vec = encoder.encode_query(text)
    assert isinstance(doc_vec, SparseVector)
    assert isinstance(query_vec, SparseVector)
    assert doc_vec.indices == query_vec.indices
    assert doc_vec.values == query_vec.values
