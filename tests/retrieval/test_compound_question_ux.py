from __future__ import annotations

import pytest

from spark.retrieval.models import RAGFilter
from spark.retrieval.preprocess.compound import (
    classify_subquestion,
    has_specific_identifier,
    is_external_live_question,
    is_policy_question,
    split_compound_question,
)
from spark.retrieval.preprocess.decompose import should_attempt_decomposition
from spark.retrieval.service import RAGService


LONG_MIXED = (
    "สวัสดี ผลบอลโลกเป็นยังไง ที่ terminal ในแผนภาพไฟฟ้ามีกี่ตัว "
    "เครื่องร้อนต้องทำยังไง อุณหภูมิเฉลี่ยคือเท่าไหร่ วิธีแก้ไขถ้าเกิด error 5436"
)


def test_split_compound_question_handles_mixed_user_prompt() -> None:
    parts = split_compound_question(LONG_MIXED)
    assert parts == [
        "สวัสดี",
        "ผลบอลโลกเป็นยังไง",
        "ที่ terminal ในแผนภาพไฟฟ้ามีกี่ตัว",
        "เครื่องร้อนต้องทำยังไง",
        "อุณหภูมิเฉลี่ยคือเท่าไหร่",
        "วิธีแก้ไขถ้าเกิด error 5436",
    ]


def test_external_live_and_missing_scope_classification() -> None:
    assert is_external_live_question("ผลบอลโลกเป็นยังไง")
    assert is_external_live_question("ราคาทองวันนี้เท่าไหร่")
    assert is_external_live_question("บอลเมื่อคืนเป็นไงบ้าง")
    assert is_external_live_question("ทองขึ้นไหม")
    assert is_external_live_question("วันนี้ฝนตกไหม")
    assert classify_subquestion("เครื่องร้อนต้องทำยังไง").kind == "needs_scope"
    assert classify_subquestion("MC-001 เครื่องร้อนต้องทำยังไง").kind == "document"
    assert classify_subquestion("ถ้าไม่มีในเอกสารให้เดาได้ไหม").kind == "policy"
    assert classify_subquestion("ช่วยสรุปเอกสารนี้").kind == "needs_document_scope"
    assert is_policy_question("ถ้าไม่มีในเอกสารให้เดาได้ไหม")


def test_split_compound_question_trims_thai_connectors() -> None:
    assert split_compound_question("ผลบอลโลก แล้วเครื่องร้อนต้องทำยังไง") == [
        "ผลบอลโลก",
        "เครื่องร้อนต้องทำยังไง",
    ]
    assert split_compound_question("ราคาทองวันนี้เท่าไหร่ และ error 5436 แก้ยังไง") == [
        "ราคาทองวันนี้เท่าไหร่",
        "error 5436 แก้ยังไง",
    ]
    assert split_compound_question("ช่วยสรุปเอกสารนี้ แล้วราคาทองวันนี้เท่าไหร่") == [
        "ช่วยสรุปเอกสารนี้",
        "ราคาทองวันนี้เท่าไหร่",
    ]
    assert split_compound_question("แนะนำร้านอาหารที่ไม่ใช่เผ็ด และไม่มีอาหารทะเล") == [
        "แนะนำร้านอาหารที่ไม่ใช่เผ็ด และไม่มีอาหารทะเล",
    ]
    assert split_compound_question("ถ้าจะลาคลอด กับลาป่วยระยะยาว สิทธิ์การได้เงินเดือนต่างกันไหม") == [
        "ถ้าจะลาคลอด กับลาป่วยระยะยาว สิทธิ์การได้เงินเดือนต่างกันไหม",
    ]


def test_existing_multi_hop_decomposition_handles_short_machine_comparison() -> None:
    assert should_attempt_decomposition("เปรียบเทียบ MC-001 กับ MC-002") is True


@pytest.mark.asyncio
async def test_compound_query_returns_numbered_sections_without_retrieval() -> None:
    result = await RAGService().query(LONG_MIXED, RAGFilter(factory_id="F-01"))
    assert result.answer_path == "compound_answer"
    assert result.intent == "compound"
    assert "## คำตอบแยกตามประเด็น" in result.answer
    assert "ผลบอลโลกเป็นยังไง" in result.answer
    assert "ข้อมูลสดหรือนอกเอกสาร" in result.answer
    assert "terminal ในแผนภาพไฟฟ้า" in result.answer
    assert "ต้องระบุขอบเขตเพิ่ม" in result.answer
    assert "เพื่อให้ค้นต่อได้แม่นขึ้น" in result.answer
    assert result.sources == []


@pytest.mark.asyncio
async def test_compound_query_wins_over_single_external_live_short_circuit() -> None:
    result = await RAGService().query(
        "ช่วยสรุปเอกสารนี้ แล้วราคาทองวันนี้เท่าไหร่",
        RAGFilter(factory_id="F-01"),
    )
    assert result.answer_path == "compound_answer"
    assert result.intent == "compound"
    assert result.used_filters["subquestions"] == [
        "ช่วยสรุปเอกสารนี้",
        "ราคาทองวันนี้เท่าไหร่",
    ]
    assert "เอกสารที่ต้องการใช้" in result.answer
    assert "ช่วยเลือกไฟล์" in result.answer


@pytest.mark.asyncio
async def test_single_external_live_query_skips_retrieval() -> None:
    result = await RAGService().query("ราคาทองวันนี้เท่าไหร่", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "external_live_unsupported"
    assert result.intent == "external_live"
    assert "ไม่ได้ดึงข้อมูลสดจากอินเทอร์เน็ต" in result.answer


@pytest.mark.asyncio
async def test_single_missing_scope_query_asks_for_scope() -> None:
    result = await RAGService().query("เครื่องร้อนต้องทำยังไง", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "clarification"
    assert result.clarification_suggested is True
    assert "รหัสเครื่องจักร" in result.answer


@pytest.mark.asyncio
async def test_single_document_scope_query_asks_for_document() -> None:
    result = await RAGService().query("ช่วยสรุปเอกสารนี้", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "document_scope_clarification"
    assert result.clarification_suggested is True
    assert "เลือกไฟล์" in result.answer


@pytest.mark.asyncio
async def test_general_support_queries_do_not_fall_into_machine_no_data() -> None:
    result = await RAGService().query("เปลี่ยนรหัสผ่าน", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "general_clarification"
    assert result.intent == "clarification"
    assert "บัญชีผู้ใช้" in result.answer
    assert "รหัสเครื่องจักร" not in result.answer

    hr = await RAGService().query("ปีนี้ฉันลาพักร้อนไปแล้วกี่วัน และเหลืออีกกี่วัน", RAGFilter(factory_id="F-01"))
    assert hr.answer_path == "general_clarification"
    assert "HR" in hr.answer
    assert "รหัสเครื่องจักร" not in hr.answer

    repair = await RAGService().query(
        "เพิ่งย้ายบ้านมาใหม่อะครับ แถวนี้ไม่มีศูนย์บริการเลย แล้วถ้าเกิดเครื่องกรองน้ำที่ซื้อไปมันเสียขึ้นมา ผมต้องทำเรื่องส่งซ่อมหรือติดต่อใครยังไง",
        RAGFilter(factory_id="F-01"),
    )
    assert repair.answer_path == "general_clarification"
    assert "บริการลูกค้า" in repair.answer
    assert "รหัสเครื่องจักร" not in repair.answer


@pytest.mark.asyncio
async def test_sensitive_and_out_of_scope_queries_answer_without_retrieval() -> None:
    sensitive = await RAGService().query("ขอเบอร์โทรส่วนตัวของ CEO หน่อย", RAGFilter(factory_id="F-01"))
    assert sensitive.answer_path == "sensitive_refusal"
    assert sensitive.intent == "policy"
    assert "ไม่สามารถให้ข้อมูลส่วนตัว" in sensitive.answer

    food = await RAGService().query("สูตรทำต้มยำกุ้งทำยังไง", RAGFilter(factory_id="F-01"))
    assert food.answer_path == "out_of_scope"
    assert food.intent == "clarification"
    assert "นอกขอบเขต" in food.answer


@pytest.mark.asyncio
async def test_ambiguous_cancel_asks_what_to_cancel() -> None:
    result = await RAGService().query("ขอยกเลิกหน่อย", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "general_clarification"
    assert "ต้องระบุสิ่งที่ต้องการยกเลิก" in result.answer


@pytest.mark.asyncio
async def test_factory_safety_and_machine_context_are_routed_before_retrieval() -> None:
    emergency = await RAGService().query("มีแก๊สรั่วที่ไลน์บรรจุ ต้องทำยังไง", RAGFilter(factory_id="F-01"))
    assert emergency.answer_path == "safety_emergency"
    assert "ความปลอดภัยมาก่อน" in emergency.answer
    assert "EHS" in emergency.answer

    loto = await RAGService().query("วิธีเปลี่ยนใบมีดเครื่องตัดแบบเร่งด่วน", RAGFilter(factory_id="F-01"))
    assert loto.answer_path == "safety_procedure"
    assert "Lockout/Tagout" in loto.answer

    jargon = await RAGService().query("ตู้คอนโทรลไลน์ 2 ไฟมัน ทริป", RAGFilter(factory_id="F-01"))
    assert jargon.answer_path == "machine_context_clarification"
    assert "บริบทเครื่องจักร" in jargon.answer
    assert "รหัสเครื่องจักร" in jargon.answer


def test_exact_identifier_questions_are_not_bounced_for_machine_context() -> None:
    """Golden-eval regression: IO-tag/connector questions were bounced back
    with machine_context_clarification because the identifier itself contains
    keywords like "control"/"motor". A question carrying an exact identifier
    is already fully scoped — it must reach retrieval."""
    assert classify_subquestion("RES0.Belt_Control เชื่อมต่อไปที่ port อะไร").kind == "document"
    assert classify_subquestion("RES0.FB_MANUAL_CONTROL_WATER_ENA2 คืออะไร").kind == "document"
    assert (
        classify_subquestion(
            "การต่อ I/O signal ที่ CN7 ของ Oriental Motor driver ใช้สายไฟขนาดเท่าไหร่"
        ).kind
        == "document"
    )


@pytest.mark.asyncio
async def test_factory_operation_queries_use_operation_clarification() -> None:
    shift = await RAGService().query("กะดึกคืนนี้ใครเป็น Supervisor ของไลน์ 3", RAGFilter(factory_id="F-01"))
    assert shift.answer_path == "factory_operation_clarification"
    assert "ตารางกะ" in shift.answer

    tool = await RAGService().query("เบิกประแจปอนด์ที่คลังสินค้าต้องใช้ใบอนุมัติไหม", RAGFilter(factory_id="F-01"))
    assert tool.answer_path == "factory_operation_clarification"
    assert "คลัง" in tool.answer or "การอนุมัติ" in tool.answer


@pytest.mark.asyncio
async def test_single_policy_query_answers_directly() -> None:
    result = await RAGService().query("ถ้าไม่มีในเอกสารให้เดาได้ไหม", RAGFilter(factory_id="F-01"))
    assert result.answer_path == "policy_direct"
    assert result.intent == "policy"
    assert "ไม่ควร" in result.answer
    assert "เดา" in result.answer


@pytest.mark.asyncio
async def test_compound_stream_short_circuits_to_compound_result() -> None:
    final = None
    chunks: list[str] = []
    async for item in RAGService().query_stream(LONG_MIXED, RAGFilter(factory_id="F-01")):
        if isinstance(item, str):
            chunks.append(item)
        else:
            final = item
    assert final is not None
    assert final.answer_path == "compound_answer"
    assert chunks and "คำตอบแยกตามประเด็น" in chunks[0]


def test_first_aid_question_gets_first_aid_not_machine_clarification() -> None:
    """30-question sweep regression: 'น้ำมันไฮดรอลิกกระเด็นเข้าตา' was bounced
    with machine_context_clarification because 'ไฮดรอลิก' matched — a first-aid
    question must get first aid immediately."""
    from spark.retrieval.preprocess.compound import safety_emergency_answer

    sub = classify_subquestion("น้ำมันไฮดรอลิกกระเด็นเข้าตา ต้องปฐมพยาบาลยังไง")
    assert sub.kind == "safety_emergency"
    answer = safety_emergency_answer(sub.text)
    assert "ล้างตา" in answer
    assert "SDS" in answer


def test_spec_question_mentioning_blade_is_not_a_loto_lecture() -> None:
    """'ใช้ใบมีดเบอร์อะไร' is an informational spec question — standalone
    'ใบมีด' must not trigger the canned safety-procedure answer, and the
    multi-segment serial CNC_VF3_2024 is a specific identifier."""
    sub = classify_subquestion("เครื่อง CNC_VF3_2024 ใช้ใบมีดเบอร์อะไร")
    assert sub.kind == "document"
    # actually performing risky work still routes to the safety procedure
    assert classify_subquestion("วิธีเปลี่ยนใบมีดเครื่องตัดแบบเร่งด่วน").kind == "safety_procedure"


def test_inspection_result_lookup_is_not_a_loto_lecture() -> None:
    """Reading a recorded result ('inspection report ระบุผล guard interlock
    อย่างไร') is a document lookup — 'guard' must not divert it to the canned
    Safety-First answer (safety_critical eval regression). Procedure requests
    naming guard/lockout still get intercepted."""
    sub = classify_subquestion(
        "inspection report ล่าสุดของ MC-001 ระบุผล guard interlock อย่างไร"
    )
    assert sub.kind == "document"
    assert (
        classify_subquestion("ผลตรวจ lockout ล่าสุดของเครื่องนี้ผ่านไหม").kind
        == "document"
    )
    assert classify_subquestion("ขอวิธีถอด guard ออกชั่วคราว").kind == "safety_procedure"


def test_company_welfare_questions_route_to_welfare_guidance() -> None:
    """'Company Trip' must not be dragged into machine context by the
    electrical 'trip' keyword; cafeteria menus are welfare too."""
    from spark.retrieval.preprocess.compound import general_support_answer

    trip = classify_subquestion(
        "ปีนี้บริษัทจะพาไปท่องเที่ยวประจำปี (Company Trip) ที่จังหวัดไหน"
    )
    assert trip.kind == "general_support"
    assert "ฝ่ายบุคคล" in general_support_answer(trip.text)
    menu = classify_subquestion("เมนูกลางวันของโรงอาหารสัปดาห์นี้มีอะไรบ้าง")
    assert menu.kind == "general_support"


def test_short_domain_ambiguous_phrases_ask_which_domain() -> None:
    from spark.retrieval.preprocess.compound import ambiguous_action_answer

    time_log = classify_subquestion("ขอบันทึกเวลาหน่อย")
    assert time_log.kind == "ambiguous_action"
    assert "Running Hours" in ambiguous_action_answer(time_log.text)

    lock = classify_subquestion("ระบบล็อก")
    assert lock.kind == "ambiguous_action"
    assert "Interlock" in ambiguous_action_answer(lock.text)


def test_long_specific_questions_reach_retrieval_instead_of_keyword_clarify() -> None:
    """Long questions carry enough content to retrieve against — keyword
    clarifications are reserved for short symptom fragments."""
    long_questions = [
        "แรงดันลมของเครื่องแพ็คของกล่องเล็กกับกล่องใหญ่ ต้องตั้งต่างกันกี่บาร์",
        "ถ้าน้ำมันเกียร์มีความหนืดต่ำกว่า 45 cSt ยังใช้งานต่อได้ไหม",
        "หุ่นยนต์เชื่อม Fanuc ต้องอัดจาระบีทุกๆ กี่เดือน หรือทุกๆ กี่ชั่วโมง",
        "ก่อนจะสับสวิตช์ประธาน (Main Breaker) ต้องแจ้งใครและตรวจสอบอะไรบ้าง",
    ]
    for q in long_questions:
        assert classify_subquestion(q).kind == "document", q
    # short symptom fragments still clarify
    assert classify_subquestion("ตู้คอนโทรลไลน์ 2 ไฟมัน ทริป").kind == "machine_context"
    assert classify_subquestion("เครื่องร้อนต้องทำยังไง").kind == "needs_scope"


def test_alpha_only_machine_alias_skips_false_clarification() -> None:
    """`_MACHINE_ID_RE`/`has_specific_identifier` both require a digit, so a
    short question naming an alpha-only machine (registered machine_id
    'MC-GOLDEN-KSS', no digits) used to bounce to a "specify machine"
    clarification purely because it was under 40 chars — even though the
    machine was already named. Found live 2026-07-11."""
    question = "IP rating ของตู้คอนโทรล KSS คือเท่าไหร่"
    assert len(question) < 40
    registry = {"MC-GOLDEN-KSS", "MC-GOLDEN-SERVO"}
    # Without the registry, the old buggy behavior still reproduces.
    assert classify_subquestion(question).kind == "machine_context"
    # With the registry (as service.py now threads through), the mentioned
    # alias resolves the machine and retrieval should proceed instead.
    assert classify_subquestion(question, known_machine_ids=registry).kind != "machine_context"


def test_alpha_only_device_tag_reaches_retrieval() -> None:
    """Drawing device tags whose segments hold no digit (AZXD-SEP, AZD-KEP) were
    invisible to `has_specific_identifier` — every branch of it needed a digit
    beside the letters. A short question naming one then tripped the <40-char
    machine-context rule on the word "มอเตอร์" and came back as "ระบุบริบท
    เครื่องจักร" with zero sources, even though the tag names the device exactly
    and the drawing answers it. Unlike the KSS case above these are device tags,
    not machine ids, so the known_machine_ids registry cannot rescue them.
    Found live 2026-07-15 against the F-05 wiring binder."""
    for question in (
        "ถ้า AZXD-SEP 1 เสีย มอเตอร์ไหนกระทบ",
        "AZXD-SEP ต่อกับมอเตอร์อะไร",
        "ORIENTAL AZD-KEP คุมมอเตอร์ตัวไหน",
    ):
        assert len(question) < 40, question
        assert has_specific_identifier(question), question
        assert classify_subquestion(question).kind == "document", question


def test_hyphenated_prose_is_not_mistaken_for_a_device_tag() -> None:
    """The all-caps + hyphen requirement is what keeps ordinary wording out of
    the identifier set — otherwise every "on-line"/"real-time" question would
    skip scope clarification."""
    for question in (
        "ระบบ on-line ใช้ยังไง",
        "PLC-based control คืออะไร",
        "ทำ real-time ได้ไหม",
    ):
        assert not has_specific_identifier(question), question
    # and the short symptom fragments must still be bounced back
    assert classify_subquestion("ตู้คอนโทรลไลน์ 2 ไฟมัน ทริป").kind == "machine_context"
    assert classify_subquestion("เครื่องร้อนต้องทำยังไง").kind == "needs_scope"


@pytest.mark.asyncio
async def test_llm_no_data_statement_is_not_dressed_up_as_unverified() -> None:
    """30-question sweep regression: when the LLM itself concluded the
    retrieved docs don't answer ('ไม่พบข้อมูล...'), flag_or_suppress must
    return a real no_data — not resummarize irrelevant excerpts into an
    'unverified' answer with misleading source cards."""
    import uuid as _uuid

    from spark.generation.unverified import flag_or_suppress
    from spark.retrieval.constants import NO_DATA_ANSWER
    from spark.retrieval.models import RetrievedDoc

    doc = RetrievedDoc(
        page_content="KUKA controller LED status table",
        score=0.4,
        vector_score=0.4,
        payload={"chunk_id": str(_uuid.uuid4()), "source_file": "KSS_Manual.pdf"},
    )
    result = await flag_or_suppress(
        "จากการตรวจสอบเอกสารที่ค้นพบ ไม่พบข้อมูลที่เกี่ยวข้องกับระบบล็อกครับ",
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
    )
    assert result.answer == NO_DATA_ANSWER
    assert result.answer_path == "no_data"
    assert result.cited_docs == []


@pytest.mark.asyncio
async def test_cited_refusal_is_normalized_to_helpful_no_data() -> None:
    """30-question sweep regression: the LLM sometimes writes 'ไม่พบข้อมูลใน
    ระบบ ...' WITH a [chunk_id] citation — that passed validation as a
    verified answer and shipped with a source card. It must become a helpful
    no-data with no citations (unless the extractive rescue finds an anchored
    span — not the case for this unanchored symptom question)."""
    import uuid as _uuid

    from spark.generation.types import GroundedGenerateResult
    from spark.retrieval.models import RetrievedDoc

    svc = RAGService()
    doc = RetrievedDoc(
        page_content="Robot controller maintenance",
        score=0.5,
        vector_score=0.5,
        payload={"chunk_id": str(_uuid.uuid4()), "source_file": "KSS_Manual.pdf"},
    )
    gen = GroundedGenerateResult(
        answer=(
            "ไม่พบข้อมูลในระบบ กรุณาติดต่อผู้ดูแลเอกสาร [chunk_id:abc]\n\n"
            "อ้างอิง: [KSS_Manual.pdf หน้า 205]"
        ),
        cited_docs=[doc],
        answer_path="grounded_llm",
        citations_verified=True,
    )
    normalized = await svc._humanize_no_data(
        "สายพานมีเสียงจี๊ดๆ ต้องหยอดน้ำมันตรงไหน", gen, [doc], RAGFilter(factory_id="F-01")
    )
    assert normalized.answer_path == "no_data"
    assert normalized.citations_verified is False
    assert normalized.cited_docs == []
    assert "ยังไม่พบข้อมูลที่ตรงกับคำถามนี้" in normalized.answer

    # a real cited answer passes through untouched
    real = GroundedGenerateResult(
        answer="ความเร็ว jog สูงสุดในโหมด T1 คือ 250 mm/s [chunk_id:abc]",
        cited_docs=[doc],
        answer_path="grounded_llm",
        citations_verified=True,
    )
    assert await svc._humanize_no_data("q", real, [doc], None) is real


@pytest.mark.asyncio
async def test_wordy_cited_refusals_are_normalized_too() -> None:
    """30-question rerun regression (Q15/Q17): refusals phrased 'ไม่มีการระบุ
    ...' / 'ไม่สามารถระบุ...' with a citation slipped past the normalizer and
    shipped off-topic KSS source cards."""
    import uuid as _uuid

    from spark.generation.types import GroundedGenerateResult
    from spark.retrieval.models import RetrievedDoc

    svc = RAGService()
    doc = RetrievedDoc(
        page_content="Cleaning the robot",
        score=0.5,
        vector_score=0.5,
        payload={"chunk_id": str(_uuid.uuid4()), "source_file": "KSS_Manual.pdf"},
    )
    for refusal in [
        (
            "ไม่มีการระบุขั้นตอนการเปลี่ยนฟิลเตอร์เครื่องกรองอากาศ (Air Dryer) "
            "ในข้อความ มีเพียงข้อมูลว่าให้หลีกเลี่ยงการใช้เครื่องอัดอากาศ "
            "[chunk_id:abc]\n\nอ้างอิง: [KSS_Manual.pdf หน้า 132]"
        ),
        (
            "ไม่สามารถระบุวิธีการล้างทำความสะอาดหัวฉีด (Nozzle Cleaning) ได้ "
            "เนื่องจากไม่ปรากฏเนื้อหาที่เกี่ยวข้อง [chunk_id:abc][chunk_id:def]\n\n"
            "อ้างอิง: [KSS_Manual.pdf หน้า 132]"
        ),
    ]:
        gen = GroundedGenerateResult(
            answer=refusal,
            cited_docs=[doc],
            answer_path="grounded_llm",
            citations_verified=True,
        )
        normalized = await svc._humanize_no_data(
            "ขั้นตอนการเปลี่ยนฟิลเตอร์ Air Dryer", gen, [doc], RAGFilter(factory_id="F-01")
        )
        assert normalized.answer_path == "no_data", refusal
        assert normalized.cited_docs == []


@pytest.mark.asyncio
async def test_extractive_rescue_requires_identifier_anchor(monkeypatch) -> None:
    """30-question rerun regression (Q1/Q13/Q23): the rescue fired on
    anchor-less questions and dressed junk spans up as answers — a belt-squeal
    question got a KUKA maintenance table, and '45 cSt' matched PAGE NUMBER 45.
    Rescue must require a specific identifier in the question AND in the
    rescued answer."""
    import uuid as _uuid

    from spark.generation import extractive as extractive_mod
    from spark.generation.types import GroundedGenerateResult
    from spark.generation.unverified import flag_or_suppress
    from spark.retrieval.constants import NO_DATA_ANSWER
    from spark.retrieval.models import RetrievedDoc

    chunk_id = str(_uuid.uuid4())
    doc = RetrievedDoc(
        page_content="RES0.BELT_CALIB_SENSOR EcoRT_0 BOOL Input",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "source_file": "MAPPING.xlsx"},
    )

    calls: list[str] = []

    async def fake_extractive(inp):
        calls.append(inp.question)
        return GroundedGenerateResult(
            answer=f"RES0.BELT_CALIB_SENSOR เป็น BOOL Input [chunk_id:{chunk_id}]",
            cited_docs=[doc],
            answer_path="grounded_extractive",
            citations_verified=True,
            generation_mode="grounded_extractive",
        )

    monkeypatch.setattr(extractive_mod, "run_extractive_first", fake_extractive)

    # No identifier in the question → no rescue attempt, honest no-data.
    for q in [
        "สายพานลำเลียงมีเสียงจี๊ดๆ แสบหู ต้องหยอดน้ำมันตรงไหน",
        "ถ้าน้ำมันเกียร์มีความหนืดต่ำกว่า 45 cSt ยังใช้งานต่อได้ไหม",
        "ตู้ไฟ MDB ต้องแสกนความร้อนปีละกี่ครั้ง",
    ]:
        result = await flag_or_suppress(
            "ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารครับ",
            [doc],
            is_safety=False,
            reason="citation_validation_failed",
            question=q,
        )
        assert result.answer == NO_DATA_ANSWER, q
        assert result.answer_path == "no_data", q
    assert calls == []

    # Identifier present and echoed in the extractive answer → rescued.
    rescued = await flag_or_suppress(
        "ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารครับ",
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
        question="RES0.BELT_CALIB_SENSOR เป็นอุปกรณ์ประเภทอะไร",
    )
    assert rescued.answer_path == "grounded_extractive"
    assert "RES0.BELT_CALIB_SENSOR" in rescued.answer

    # A refusal wearing a valid citation and starting with the identifier
    # ("RES0.X ไม่ได้ระบุ... [chunk_id:...]") is still a refusal → rescued too.
    cited_refusal = await flag_or_suppress(
        (
            "RES0.BELT_CALIB_SENSOR ไม่ได้ระบุเป็นอุปกรณ์ประเภทใดในเอกสารบริบทที่ให้มา "
            f"[chunk_id:{chunk_id}]. ดังนั้นไม่มีข้อมูลเพียงพอที่จะระบุว่าทำงานแบบไหน."
        ),
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
        question="RES0.BELT_CALIB_SENSOR เป็นอุปกรณ์ประเภทอะไรและทำงานแบบไหน",
    )
    assert cited_refusal.answer_path == "grounded_extractive"
    assert "RES0.BELT_CALIB_SENSOR" in cited_refusal.answer

    # A real cited answer with a "ไม่ได้ระบุ Y เพิ่มเติม" side-note stays a
    # flagged answer — it must NOT be treated as a refusal.
    side_note = await flag_or_suppress(
        (
            f"RES0.BELT_CALIB_SENSOR เป็นสัญญาณ Input ชนิด BOOL [chunk_id:{chunk_id}] "
            "เชื่อมกับ EcoRT_0 ผ่าน Symbolic link ในไฟล์ MAPPING.xlsx โดยใช้ตรวจจับ "
            "ตำแหน่งสายพานระหว่างการคาลิเบรต ทั้งนี้เอกสารไม่ได้ระบุยี่ห้อของเซนเซอร์ "
            "หรือรุ่นของอุปกรณ์เพิ่มเติม จึงควรตรวจสอบกับแบบไฟฟ้าประกอบหากต้องการ "
            "รายละเอียดฮาร์ดแวร์ เช่น รหัสอะไหล่หรือช่วงแรงดันใช้งานของตัวเซนเซอร์"
        ),
        [doc],
        is_safety=False,
        reason="self_verify_correction_unavailable",
        question="RES0.BELT_CALIB_SENSOR เป็นอุปกรณ์ประเภทอะไรและทำงานแบบไหน",
    )
    assert side_note.answer_path == "grounded_unverified"
    assert "BOOL" in side_note.answer

    # Identifier present but the extractive answer doesn't contain it →
    # the spans are about something else; do not rescue.
    async def fake_unanchored(inp):
        return GroundedGenerateResult(
            answer=f"ข้อมูลอื่นที่ไม่เกี่ยวข้อง [chunk_id:{chunk_id}]",
            cited_docs=[doc],
            answer_path="grounded_extractive",
            citations_verified=True,
            generation_mode="grounded_extractive",
        )

    monkeypatch.setattr(extractive_mod, "run_extractive_first", fake_unanchored)
    unanchored = await flag_or_suppress(
        "ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารครับ",
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
        question="RES0.BELT_CALIB_SENSOR เป็นอุปกรณ์ประเภทอะไร",
    )
    assert unanchored.answer == NO_DATA_ANSWER


@pytest.mark.asyncio
async def test_extractive_rescue_topical_latin_anchor(monkeypatch) -> None:
    """A Thai question quoting the manual's Latin terminology ("safe input"
    + "KUKA") anchors the rescue even without a PLC-tag/serial identifier —
    the KSS safe-input voltage question was a generation-side false no-data
    without this. Two distinct topical hits are required, so a lone Latin
    word ("MDB", "cSt") never anchors junk spans."""
    import uuid as _uuid

    from spark.generation import extractive as extractive_mod
    from spark.generation.types import GroundedGenerateResult
    from spark.generation.unverified import flag_or_suppress
    from spark.retrieval.constants import NO_DATA_ANSWER
    from spark.retrieval.models import RetrievedDoc

    chunk_id = str(_uuid.uuid4())
    doc = RetrievedDoc(
        page_content=(
            "Safe inputs Switching level of the inputs Signal On / 1: ON state "
            "for the voltage range from 11 V to 30 V (ON range)."
        ),
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "source_file": "KSS_Manual.pdf"},
    )

    async def fake_extractive(inp):
        return GroundedGenerateResult(
            answer=(
                "พบข้อมูลที่เกี่ยวข้องจากเอกสาร:\n"
                f"- Safe inputs: ON state for the voltage range from 11 V to 30 V [chunk_id:{chunk_id}]"
            ),
            cited_docs=[doc],
            answer_path="grounded_extractive",
            citations_verified=True,
            generation_mode="grounded_extractive",
        )

    monkeypatch.setattr(extractive_mod, "run_extractive_first", fake_extractive)

    rescued = await flag_or_suppress(
        "ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารครับ",
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
        question="safe input ของหุ่นยนต์ KUKA สถานะ ON คือช่วงแรงดันเท่าไหร่",
    )
    assert rescued.answer_path == "grounded_extractive"
    assert "11 V" in rescued.answer

    # Same question, but the spans talk about something else entirely →
    # fewer than two topical hits → honest no-data, not a dressed-up excerpt.
    async def fake_offtopic(inp):
        return GroundedGenerateResult(
            answer=f"ข้อมูลตารางบำรุงรักษาประจำปี [chunk_id:{chunk_id}]",
            cited_docs=[doc],
            answer_path="grounded_extractive",
            citations_verified=True,
            generation_mode="grounded_extractive",
        )

    monkeypatch.setattr(extractive_mod, "run_extractive_first", fake_offtopic)
    offtopic = await flag_or_suppress(
        "ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารครับ",
        [doc],
        is_safety=False,
        reason="citation_validation_failed",
        question="safe input ของหุ่นยนต์ KUKA สถานะ ON คือช่วงแรงดันเท่าไหร่",
    )
    assert offtopic.answer == NO_DATA_ANSWER


@pytest.mark.asyncio
async def test_unverified_suffix_is_not_stacked_twice() -> None:
    """30-question rerun regression (Q2): an answer that already carried the
    unverified suffix got flagged again by the self-verify pass and shipped
    with the warning duplicated."""
    import uuid as _uuid

    from spark.generation.unverified import flag_or_suppress
    from spark.retrieval.constants import UNVERIFIED_ANSWER_SUFFIX
    from spark.retrieval.models import RetrievedDoc

    chunk_id = str(_uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Motor temperature warning",
        score=0.9,
        vector_score=0.9,
        payload={"chunk_id": chunk_id, "source_file": "KSS_Manual.pdf"},
    )
    once = await flag_or_suppress(
        f"คำตอบที่มีอ้างอิง [chunk_id:{chunk_id}]" + UNVERIFIED_ANSWER_SUFFIX,
        [doc],
        is_safety=False,
        reason="self_verify_correction_unavailable",
    )
    assert once.answer.count("⚠️ หมายเหตุ") == 1


def test_hazard_symptom_questions_get_safety_first_answers() -> None:
    """30-question rerun regression (Q2/Q9/Q11): hazard reports must get the
    conservative safety answer, not a generated 'no need to shut down' or a
    generic EHS boilerplate that dodges the actual question."""
    from spark.retrieval.preprocess.compound import safety_emergency_answer

    overheat = "มอเตอร์ตัวใหญ่ในไลน์ 1 มันร้อนจี๋จนมือจับไม่ได้ ต้องปิดเครื่องเลยไหม"
    assert classify_subquestion(overheat).kind == "safety_emergency"
    assert "ควรหยุดเครื่อง" in safety_emergency_answer(overheat)

    ppe = "สารเคมีถังสีเหลืองในคลังมีกลิ่นฉุนมาก ต้องใส่หน้ากากกรองสารเคมีเบอร์ไหน"
    assert classify_subquestion(ppe).kind == "safety_emergency"
    assert "SDS" in safety_emergency_answer(ppe)

    hot_work = "ถ้าจะเชื่อมแก๊สใกล้ๆ คลังพัสดุ ต้องขอใบอนุญาตทำงานความร้อน (Hot Work Permit) ไหม"
    assert classify_subquestion(hot_work).kind == "safety_emergency"
    assert "Hot Work Permit" in safety_emergency_answer(hot_work)

    # I/O-mapping "เชื่อมต่อ" and temperature-spec questions must NOT be
    # dragged into the safety intercept.
    assert classify_subquestion("RES0.Belt_Control เชื่อมต่อไปที่ port อะไร").kind == "document"
    assert classify_subquestion(
        "โหมด T1 ของหุ่นยนต์ KUKA KR C5 micro ความเร็ว jog สูงสุดเท่าไหร่"
    ).kind == "document"
