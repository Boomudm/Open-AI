from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.retrieval.models import RAGStreamPhaseMeta
from spark.schemas.rag import AskRequest, RAGFilterModel
from spark.services.chat_orchestrator import ChatOrchestrator
from spark.services.intent_classifier import QuestionRouting, route_question


def test_followup_routes_to_rag() -> None:
    routing = route_question(
        "แล้วเดือนนี้ downtime กี่ชม",
        has_prior_user_message=True,
    )
    assert routing.route == "rag"


@pytest.mark.asyncio
async def test_stream_emits_meta_and_done(monkeypatch) -> None:
    orchestrator = ChatOrchestrator()
    session_id = uuid.uuid4()
    session_obj = SimpleNamespace(
        session_id=session_id,
        context={"machine_id": "MC-001"},
        title="new chat",
    )
    req = AskRequest(
        question="MC-001 bearing รุ่นอะไร",
        top_k=4,
        stream=True,
        filter=RAGFilterModel(machine_id="MC-001"),
    )

    routing = QuestionRouting(route="rag", is_followup=False, reason="default:factual")
    monkeypatch.setattr(
        "spark.services.chat_orchestrator.resolve_routing",
        AsyncMock(return_value=routing),
    )
    monkeypatch.setattr(
        "spark.services.chat_orchestrator.allowed_doc_ids_for_principal",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(orchestrator, "_lookup_validated_qa_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(
        orchestrator,
        "_prepare_rag_retrieval",
        AsyncMock(return_value=(req.question, None, [], {})),
    )
    monkeypatch.setattr(orchestrator, "_factory_rag_tuning", AsyncMock(return_value=(4, None)))
    monkeypatch.setattr(orchestrator, "_record_audit", AsyncMock())
    monkeypatch.setattr("spark.services.chat_ask_dedupe.remember_ask", AsyncMock())
    monkeypatch.setattr("spark.services.chat_ask_dedupe.finish_stream_ask", AsyncMock())
    monkeypatch.setattr(
        "spark.services.session_title_service.generate_session_title",
        AsyncMock(return_value="MC-001 bearing"),
    )

    @asynccontextmanager
    async def _noop_admission(*_args, **_kwargs):
        yield

    monkeypatch.setattr(
        "spark.retrieval.safety.admission.rag_admission_guard",
        _noop_admission,
    )

    rag_result = SimpleNamespace(
        answer="SKF 6205-2RS",
        sources=[{"doc_id": str(uuid.uuid4()), "source_file": "manual.pdf"}],
        used_filters={"answer_path": "grounded_llm", "compressed_question": "bearing model"},
        fallback_level=0,
        top_doc_score=0.7,
        retrieval_snapshot={"chunk_ids": []},
        answer_path="grounded_llm",
        citations_verified=True,
        cited_docs=[],
        retrieval_report={},
        system_degradation=None,
    )

    async def fake_stream(self, **_kwargs):
        yield RAGStreamPhaseMeta(
            retrieval_report={"degraded": False},
            system_degradation={"degraded": False, "fail_closed": False},
        )
        yield "SKF"
        yield rag_result

    from spark.retrieval.service import RAGService

    monkeypatch.setattr(RAGService, "query_stream", fake_stream)

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.get = AsyncMock(return_value=session_obj)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "spark.core.database.AsyncSessionLocal",
        lambda: _SessionCtx(),
    )

    frames: list[str] = []
    async for frame in orchestrator._ask_stream_body(session_obj, req, None, 0.0):
        frames.append(frame)

    events = []
    for frame in frames:
        if frame.startswith("event:"):
            name = frame.split("\n", 1)[0].replace("event:", "").strip()
            data_line = next(
                (ln for ln in frame.split("\n") if ln.startswith("data:")),
                "data: {}",
            )
            payload = json.loads(data_line.replace("data:", "", 1).strip())
            events.append((name, payload))

    event_names = [name for name, _ in events]
    assert "meta" in event_names
    assert "done" in event_names
    done_payload = next(payload for name, payload in events if name == "done")
    assert done_payload.get("confidence_tier") in ("high", "medium", "low")
    assert done_payload.get("assistant_message_id")
    assert done_payload.get("citations_verified") is True
    assert done_payload.get("answer_path") == "grounded_llm"
