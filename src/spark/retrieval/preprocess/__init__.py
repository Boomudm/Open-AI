"""Retrieval preprocessing — rewrite, follow-up, compression (Phase 11)."""

from spark.retrieval.preprocess.compress import maybe_compress_question
from spark.retrieval.preprocess.contextualize import contextualize_question, source_labels_from_sources
from spark.retrieval.preprocess.follow_up import is_follow_up_question
from spark.retrieval.preprocess.follow_up_boost import boost_follow_up_chunks
from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval, rules_rewrite_for_retrieval

__all__ = [
    "boost_follow_up_chunks",
    "contextualize_question",
    "is_follow_up_question",
    "maybe_compress_question",
    "rewrite_for_retrieval",
    "rules_rewrite_for_retrieval",
    "source_labels_from_sources",
]
