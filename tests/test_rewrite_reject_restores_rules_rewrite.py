"""Phase 12 — rewrite guard restores rules-based rewrite on LLM rejection."""

from __future__ import annotations

import pytest

from spark.services.session_slots import SessionSlots


@pytest.mark.asyncio
async def test_rewrite_reject_restores_rules_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval

    slots = SessionSlots(
        machine_id="MC-001",
        locked_fields=["machine_id"],
    )

    class DroppingLLM:
        async def ainvoke(self, _messages):
            class Response:
                content = "generic overheating troubleshooting"

            return Response()

    monkeypatch.setattr(
        "spark.retrieval.preprocess.rewrite.get_chat_llm",
        lambda *_args, **_kwargs: DroppingLLM(),
    )

    # A machine-id-bearing question is deliberately treated as standalone (no
    # LLM rewrite), so the guard path needs a genuinely dependent follow-up.
    rewritten, meta = await rewrite_for_retrieval(
        "overheating เพิ่มเติมหน่อย",
        [("human", "MC-001 alarm yesterday")],
        slots,
        llm_rewrite_enabled=True,
        has_prior_user_message=True,
    )
    assert "MC-001" in rewritten
    assert meta["strategy"] == "rules_fallback"
    assert meta["rewrite_verdict"] == "locked_machine_dropped"
    assert meta.get("rewrite_rejected") == "locked_machine_dropped"


@pytest.mark.asyncio
async def test_rewrite_guard_accepts_llm_when_locked_machine_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval

    slots = SessionSlots(
        machine_id="MC-001",
        locked_fields=["machine_id"],
    )

    class GoodLLM:
        async def ainvoke(self, _messages):
            class Response:
                content = "MC-001 servo overheating troubleshooting"

            return Response()

    monkeypatch.setattr(
        "spark.retrieval.preprocess.rewrite.get_chat_llm",
        lambda *_args, **_kwargs: GoodLLM(),
    )

    rewritten, meta = await rewrite_for_retrieval(
        "overheating เพิ่มเติมหน่อย",
        [("human", "MC-001 alarm yesterday")],
        slots,
        llm_rewrite_enabled=True,
        has_prior_user_message=True,
    )
    assert rewritten.startswith("MC-001")
    assert meta["strategy"] == "llm"
    assert meta["rewrite_verdict"] == "accepted"
