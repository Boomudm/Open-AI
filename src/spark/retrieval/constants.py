from __future__ import annotations

# Absolute relevance gate (cross-encoder probability, or normalized RRF when CE unavailable).
# Both signals are calibrated to [0, 1]: CE relevant pairs ~0.8–0.99, irrelevant <0.1;
# RRF top-of-one-list ≈ 0.5.
MIN_RERANK_SCORE = 0.35       # max relevance across retained docs must clear this
MIN_RERANK_AVG_SCORE = 0.25   # mean of the top-3 relevances must clear this

# A retrieved document must reach this authoritative relevance to be treated as a
# trustworthy synthesis source (manual/SOP step extraction, etc.).
MIN_RELEVANT_DOC_SCORE = 0.35

# Extractive snippet selection still uses the lexical evidence scale (see scoring.py).
MIN_EXTRACTIVE_EVIDENCE_SCORE = 0.22

# Secondary same-script lexical evidence gate (defers to dense + CE for cross-lingual).
MIN_EVIDENCE_SCORE = 0.18

# Repair-history excerpt selection minimum lexical overlap.
MIN_LEXICAL_FOR_REPAIR = 0.008

# Safety / LOTO / SOP tier — elevated relevance gate (Phase 7).
SAFETY_LOTO_MIN_MAX_SCORE = 0.45
SAFETY_LOTO_MIN_AVG_SCORE = 0.35
SAFETY_SOP_MIN_MAX_SCORE = 0.40
SAFETY_SOP_MIN_AVG_SCORE = 0.30

NO_DATA_ANSWER = "ไม่พบข้อมูลในระบบ กรุณาติดต่อวิศวกร"
UNAVAILABLE_ANSWER = "ระบบ AI ไม่พร้อมชั่วคราว กรุณาติดต่อวิศวกร"
# Appended to answers that generated real, cited content but did not fully clear
# the grounding gates (self-verify / citation coverage). For NON-safety questions
# we show the answer with this flag rather than replacing it with NO_DATA, so a
# correct answer is never silently discarded — the user verifies against the
# cited source. Safety content still fails closed. It is a SUFFIX so it can be
# emitted as trailing tokens after an answer that already streamed live.
UNVERIFIED_ANSWER_SUFFIX = (
    "\n\n⚠️ หมายเหตุ: ระบบยังยืนยันการอ้างอิงของคำตอบนี้ไม่ครบถ้วน "
    "โปรดตรวจสอบกับเอกสารต้นฉบับที่อ้างอิงก่อนนำไปใช้งานจริง"
)
