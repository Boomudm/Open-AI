"""Phase 11 — sync and stream kernel inputs differ only by stream flag."""

from __future__ import annotations

import time

from spark.retrieval.models import RAGFilter
from spark.retrieval.service import RAGService


def test_build_kernel_input_parity_except_stream() -> None:
    svc = RAGService()
    started = time.perf_counter()
    common = dict(
        question="pressure limit?",
        rf=RAGFilter(factory_id="F-01"),
        top_k=4,
        allowed_doc_ids=["doc-a"],
        synthesis_question="What is the pressure limit?",
        chat_history=[("user", "hello")],
        tuning=None,
        allow_scope_broadening=True,
        session_id="sess-123",
        question_raw="raw question",
        rewrite_meta={"strategy": "rules", "follow_up": True},
        session_slots={"turn_count": 2, "last_evidence_turn": 1},
        follow_up=True,
        last_retrieved_chunk_ids=["chunk-1"],
        deadline_started_at=started,
    )

    sync_inp = svc._build_kernel_input(**common, stream=False)
    stream_inp = svc._build_kernel_input(**common, stream=True)

    sync_fields = {k: v for k, v in sync_inp.__dict__.items() if k != "stream"}
    stream_fields = {k: v for k, v in stream_inp.__dict__.items() if k != "stream"}
    assert sync_fields == stream_fields
    assert sync_inp.stream is False
    assert stream_inp.stream is True
