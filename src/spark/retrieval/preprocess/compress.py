"""Compress long user questions before retrieval (Phase 11)."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from spark.core.config import settings
from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger

log = get_logger(__name__)

_COMPRESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "สรุปข้อความยาวเป็นคำถามหลัก 1-3 ประโยคภาษาไทย สำหรับค้นหาเอกสารโรงงาน "
            "คงรหัสเครื่อง MC-xxx และคำสำคัญเทคนิค ตอบเฉพาะคำถามที่สรุปแล้ว",
        ),
        ("human", "{question}"),
    ]
)


async def maybe_compress_question(question: str) -> tuple[str, str | None]:
    """Return (question_for_retrieval, compressed_form_or_none)."""
    threshold = settings.query_compress_char_threshold
    if len(question) <= threshold:
        return question, None

    profile = settings.query_compress_profile
    chain = _COMPRESS_PROMPT | get_chat_llm(profile)
    try:
        response = await chain.ainvoke({"question": question[: settings.question_max_length]})
        compressed = (
            response.content.strip()
            if hasattr(response, "content")
            else str(response).strip()
        )
        if not compressed or len(compressed) < 8:
            return question, None
        log.info(
            "query_compressed",
            original_len=len(question),
            compressed_len=len(compressed),
        )
        return compressed, compressed
    except Exception as exc:
        log.warning("query_compress_failed", error=str(exc)[:200])
        return question, None
