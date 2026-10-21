"""Phase 15 — runtime ingest swap eval gate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.ingestion.context import IngestContext
from spark.ingestion.embed_lineage import CHUNK_SCHEMA_VERSION
from spark.ingestion.eval_gate import (
    BreakingChangeSnapshot,
    breaking_change_detected,
    current_breaking_snapshot,
    require_swap_eval_token,
)
from spark.ingestion.errors import PermanentIngestError


def test_breaking_change_detected_on_embed_model_change() -> None:
    prior = BreakingChangeSnapshot(
        embed_model_id="old-model",
        sparse_encoder_id="bge_m3",
        chunk_schema_version=CHUNK_SCHEMA_VERSION,
        ingest_policy_version="1",
    )
    current = BreakingChangeSnapshot(
        embed_model_id="new-model",
        sparse_encoder_id="bge_m3",
        chunk_schema_version=CHUNK_SCHEMA_VERSION,
        ingest_policy_version="1",
    )
    assert breaking_change_detected(prior, current) is True


def test_breaking_change_not_detected_when_unchanged() -> None:
    snap = current_breaking_snapshot()
    assert breaking_change_detected(snap, snap) is False


@pytest.mark.asyncio
async def test_require_swap_eval_token_skipped_in_test_profile(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "test")
    monkeypatch.setattr(settings, "spark_testing", True)

    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id="MC-001",
        document_type="machine_manual",
        file_hash_sha256=None,
        document_context={},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
        is_reingest=True,
    )
    session = AsyncMock()
    await require_swap_eval_token(ctx, session)


@pytest.mark.asyncio
async def test_require_swap_eval_token_blocks_without_token(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")
    monkeypatch.setattr(settings, "spark_testing", False)

    doc_id = uuid.uuid4()
    ctx = IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id="MC-001",
        document_type="machine_manual",
        file_hash_sha256=None,
        document_context={},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
        is_reingest=True,
    )

    doc = MagicMock()
    doc.chunks_count = 4
    doc.active_ingest_generation = 1
    doc.policy_scan_version = "old-policy"

    session = AsyncMock()
    session.get = AsyncMock(return_value=doc)
    session.execute = AsyncMock(
        return_value=MagicMock(
            first=MagicMock(
                return_value=(
                    "old-embed-model",
                    CHUNK_SCHEMA_VERSION,
                    {"sparse_encoder_id": "none"},
                )
            )
        )
    )

    monkeypatch.setattr(
        "spark.ingestion.eval_gate.current_breaking_snapshot",
        lambda: BreakingChangeSnapshot(
            embed_model_id="new-embed-model",
            sparse_encoder_id="bge_m3",
            chunk_schema_version=CHUNK_SCHEMA_VERSION,
            ingest_policy_version="new-policy",
        ),
    )
    monkeypatch.setattr(
        "spark.ingestion.eval_gate.fetch_eval_token",
        AsyncMock(return_value=None),
    )

    with pytest.raises(PermanentIngestError) as exc:
        await require_swap_eval_token(ctx, session)
    assert exc.value.reason_code == "eval_gate_blocked"
