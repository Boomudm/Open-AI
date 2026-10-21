"""CJK-leak guards: a Thai factory answer must never ship Chinese/kana/hangul.

30-question rerun regression (Q1): the span translator asked a small
multilingual model for Thai and got Chinese back ("เปลี่ยน机油 使用黄油枪润滑...").
The Thai policy only measured Latin-vs-Thai ratio, so CJK sailed through every
gate and shipped to the operator.
"""

from __future__ import annotations

import pytest

from spark.generation.thai_enforce import answer_fails_thai_policy


def test_cjk_in_answer_fails_thai_policy() -> None:
    q = "สายพานลำเลียงมีเสียงจี๊ดๆ ต้องหยอดน้ำมันตรงไหน"
    assert answer_fails_thai_policy(q, "เปลี่ยน机油 使用黄油枪润滑 ตามคู่มือครับ")
    assert answer_fails_thai_policy(q, "ให้ตรวจสอบตาม手順書ครับ")
    # Thai + preserved English identifiers stay fine.
    assert not answer_fails_thai_policy(
        q, "หยอดจาระบีที่จุด lubrication ตามคู่มือ KSS หน้า 128 ครับ"
    )
    # English question → no Thai enforcement.
    assert not answer_fails_thai_policy("belt noise fix?", "使用黄油枪")


@pytest.mark.asyncio
async def test_cjk_translation_falls_back_to_original(monkeypatch) -> None:
    from spark.generation import translation as tr

    class _FakeResponse:
        content = "使用黄油枪润滑 检查齿形带张紧"

    class _FakeLLM:
        async def ainvoke(self, messages):
            return _FakeResponse()

    monkeypatch.setattr(tr, "get_chat_llm", lambda profile: _FakeLLM())
    original = "Lubricate with grease gun. Check toothed belt tension."
    assert await tr.translate_for_operator(original) == original
