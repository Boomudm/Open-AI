"""Postgres writer is a no-op in document-only RAG mode."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.index.postgres_writer import ALLOWED_POSTGRES_TABLES, PostgresRouter


def test_postgres_allowlist_is_empty() -> None:
    assert ALLOWED_POSTGRES_TABLES == frozenset()


@pytest.mark.asyncio
async def test_postgres_router_noops_for_any_table() -> None:
    router = PostgresRouter()
    session = AsyncMock()
    rec = ParsedRecord(route="postgres", payload={"part_no": "P-1"}, text_for_embedding="")
    config = {
        "postgres": {
            "table": "evil_table",
            "insert_columns": ["part_no"],
        }
    }
    written = await router.write([rec], uuid.uuid4(), config, {}, session)
    assert written == 0
    session.execute.assert_not_called()
