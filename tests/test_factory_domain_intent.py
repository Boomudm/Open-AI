"""Factory-domain intent guard for off-topic RAG rejection."""

from __future__ import annotations

from spark.retrieval.scoring import _has_sufficient_evidence
from spark.retrieval.models import RAGFilter, RetrievedDoc


def _doc(text: str) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=text,
        score=0.5,
        vector_score=0.5,
        payload={"document_type": "machine_manual", "source_file": "manual.pdf"},
    )


def test_off_topic_ramen_is_blocked() -> None:
    from spark.retrieval.scoring import _is_off_topic_factory_question

    assert _is_off_topic_factory_question("สูตรทำ ramen แบบละเอียด") is True


def test_factory_note_question_not_off_topic() -> None:
    from spark.retrieval.scoring import _is_off_topic_factory_question

    assert (
        _is_off_topic_factory_question(
            "factory note บอก target air pressure ของ MC-001 เท่าไร"
        )
        is False
    )


def test_cross_lingual_off_topic_fails_evidence_gate() -> None:
    docs = [_doc("WARNING: Check cooling fan if temperature exceeds 80°C.")]
    assert (
        _has_sufficient_evidence(
            "สูตรทำ ramen แบบละเอียด",
            RAGFilter(machine_id="MC-001"),
            docs,
        )
        is False
    )
