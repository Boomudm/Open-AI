"""Content policy blocks mark the job failed (2026-07: findings are logged
only — legacy block paths fail, never DLQ); _apply_trust_result still honors
whatever status content_policy_block_job_status returns."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.context import IngestContext, TrustScanState
from spark.ingestion.errors import PermanentIngestError, policy_block_routes_to_dlq
from spark.ingestion.job_reliability import content_policy_block_job_status
from spark.ingestion.stages.trust_stage import _apply_trust_result
from spark.ingestion.trust.models import PolicyDecision, PolicyFinding, PolicyResult


def test_content_policy_block_fails_job_without_dlq() -> None:
    assert content_policy_block_job_status() == "failed"
    assert policy_block_routes_to_dlq() is False


@pytest.mark.asyncio
async def test_apply_trust_block_uses_dlq_status() -> None:
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id="F-01",
        machine_id=None,
        document_type="machine_manual",
        file_hash_sha256="abc",
        document_context={},
        config_raw={},
        file_path=__import__("pathlib").Path("manual.pdf"),
    )
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    trust_result = PolicyResult(
        action="block",
        findings=[
            PolicyFinding(
                rule_id="injection:0",
                severity="high",
                message="injection",
                category="injection",
            )
        ],
        policy_version="3",
        risk_score=0.9,
        decision=PolicyDecision.BLOCK,
    )
    captured: dict[str, object] = {}

    async def capture_execute(stmt):
        captured["stmt"] = stmt
        return None

    session.execute = AsyncMock(side_effect=capture_execute)

    with patch(
        "spark.ingestion.stages.trust_stage.content_policy_block_job_status",
        return_value="dlq",
    ):
        with pytest.raises(PermanentIngestError):
            await _apply_trust_result(
                ctx,
                session,
                rows_total=5,
                batch=[],
                trust_result=trust_result,
                trust_state=TrustScanState(enabled=True),
            )

    assert session.execute.await_count >= 2
