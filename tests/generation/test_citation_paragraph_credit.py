"""Paragraph-level citation credit — block citations ground every sentence in the block.

An LLM that writes "fact A. fact B. [chunk_id:x]" has grounded both facts with
the block's citation; requiring a marker on each sentence rejected correct
answers purely for formatting style. Safety questions keep per-sentence
strictness.
"""

from __future__ import annotations

import uuid

from spark.generation.citations import validate_grounded_citations
from spark.generation.self_verify import extract_claims, verify_claim_against_docs
from spark.retrieval.models import RetrievedDoc


def _doc(chunk_id: str, content: str, doc_type: str = "machine_manual") -> RetrievedDoc:
    return RetrievedDoc(
        page_content=content,
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": doc_type,
            "source_file": "manual.pdf",
        },
    )


def test_paragraph_citation_covers_all_sentences_in_block() -> None:
    cid = str(uuid.uuid4())
    doc = _doc(cid, "Controller weight 25 kg. Protection rating IP66. LED blinks 4 times.")
    answer = (
        "The controller weight is 25 kg. "
        "The protection rating is IP66. "
        f"The LED blinks 4 times [chunk_id:{cid}]."
    )
    valid, cited = validate_grounded_citations(answer, [doc], question="controller spec?")
    assert valid is True
    assert len(cited) == 1


def test_multi_paragraph_each_block_cited_passes() -> None:
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())
    docs = [
        _doc(cid_a, "Motor rated speed 3000 rpm. Rated torque 2.4 Nm."),
        _doc(cid_b, "Warranty period is 24 months from delivery."),
    ]
    answer = (
        f"Motor rated speed is 3000 rpm. Rated torque is 2.4 Nm [chunk_id:{cid_a}].\n\n"
        f"Warranty period is 24 months [chunk_id:{cid_b}]."
    )
    valid, cited = validate_grounded_citations(answer, docs, question="motor spec and warranty?")
    assert valid is True
    assert len(cited) == 2


def test_uncited_block_still_fails() -> None:
    cid = str(uuid.uuid4())
    doc = _doc(cid, "Controller weight 25 kg.")
    answer = (
        f"The controller weight is 25 kg [chunk_id:{cid}].\n\n"
        "The maximum humidity is 95 percent without condensation. "
        "The storage temperature must remain constant. "
        "The unit requires annual recalibration by a technician. "
        "Replacement filters must be sourced from the vendor."
    )
    valid, _ = validate_grounded_citations(answer, [doc], question="controller spec?")
    assert valid is False


def test_safety_question_keeps_per_sentence_strictness() -> None:
    cid = str(uuid.uuid4())
    doc = _doc(cid, "LOTO: isolate power. Lock breaker. Verify zero energy.", doc_type="sop")
    # Two factual safety sentences share one block citation — for a LOTO
    # question the max uncited ratio is 0.0, so paragraph credit must NOT apply.
    answer = (
        "Isolate the power supply first. "
        f"Then lock the breaker and verify zero energy [chunk_id:{cid}]."
    )
    valid, _ = validate_grounded_citations(
        answer, [doc], question="ขั้นตอน LOTO ก่อนซ่อมเครื่องต้องทำอย่างไร"
    )
    assert valid is False


def test_extract_claims_inherits_block_citation() -> None:
    cid = str(uuid.uuid4())
    answer = (
        "อุณหภูมิสูงสุดคือ 85 องศา. "
        f"LED กระพริบ 4 ครั้ง [chunk_id:{cid}]."
    )
    claims = extract_claims(answer)
    assert len(claims) == 2
    assert all(f"[chunk_id:{cid}]" in claim for claim in claims)


def test_inherited_citation_grounds_cross_lingual_claim() -> None:
    cid = str(uuid.uuid4())
    doc = _doc(cid, "Main circuit overheat at 85 C. LED1 blinks 4 times.")
    # Thai claim over English evidence: lexical overlap ~0, but the inherited
    # block citation points at a retrieved chunk whose numbers agree.
    claim = f"อุณหภูมิสูงสุดที่ทำให้เกิด alarm คือ 85 องศา [chunk_id:{cid}]"
    verified = verify_claim_against_docs(claim, [doc])
    assert verified.supported is True


def test_valid_citation_alone_does_not_support_same_language_non_numeric_claim() -> None:
    cid = str(uuid.uuid4())
    doc = _doc(cid, "Warranty period is 24 months from delivery.")
    claim = f"The controller is waterproof for outdoor washdown [chunk_id:{cid}]"
    verified = verify_claim_against_docs(claim, [doc])
    assert verified.supported is False
