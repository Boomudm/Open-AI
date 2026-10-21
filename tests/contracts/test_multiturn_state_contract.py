"""Contract: Phase 11 multi-turn session, revision, and query rewrite."""

from __future__ import annotations


def test_phase11_preprocess_exports() -> None:
    from spark.retrieval.preprocess import (
        boost_follow_up_chunks,
        contextualize_question,
        is_follow_up_question,
        maybe_compress_question,
        rewrite_for_retrieval,
        rules_rewrite_for_retrieval,
    )
    from spark.services.session_slots import SessionSlots, merge_session_slots

    assert callable(rewrite_for_retrieval)
    assert callable(rules_rewrite_for_retrieval)
    assert callable(is_follow_up_question)
    assert callable(maybe_compress_question)
    assert callable(contextualize_question)
    assert callable(boost_follow_up_chunks)
    assert SessionSlots is not None
    assert callable(merge_session_slots)


def test_legacy_shims_still_export_preprocess() -> None:
    from spark.services.query_compression import maybe_compress_question
    from spark.retrieval.preprocess.follow_up import is_follow_up_question
    from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval

    assert callable(maybe_compress_question)
    assert callable(is_follow_up_question)
    assert callable(rewrite_for_retrieval)


def test_rag_filter_has_revision_field() -> None:
    from spark.retrieval.models import RAGFilter

    rf = RAGFilter(revision="Rev C")
    assert rf.revision == "Rev C"
