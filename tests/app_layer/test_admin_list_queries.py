"""Admin list query batching tests (app-layer Phase 4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.org import User
from spark.services.admin_user_service import count_position_usage_batch, load_admin_users_batch


def _user(idx: int) -> User:
    user_id = uuid.uuid4()
    row = User(
        user_id=user_id,
        username=f"user{idx}",
        full_name=f"User {idx}",
        email=f"user{idx}@example.com",
        password_hash="x",
        is_active=True,
        token_version=0,
        is_super_admin=False,
    )
    return row


@pytest.mark.asyncio
async def test_load_admin_users_batch_uses_bounded_queries() -> None:
    users = [_user(i) for i in range(50)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(all=lambda: [(users[0].user_id, "employee")]),
            MagicMock(
                all=lambda: [(users[0].user_id, "F-01", "read")]
            ),
            MagicMock(all=lambda: [(users[0].user_id, uuid.uuid4())]),
        ]
    )
    items = await load_admin_users_batch(session, users)
    assert len(items) == 50
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_count_position_usage_batch_single_round_trip() -> None:
    position_ids = [uuid.uuid4() for _ in range(10)]
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(all=lambda: [(position_ids[0], 3)]),
            MagicMock(all=lambda: [(position_ids[0], 2)]),
        ]
    )
    usage = await count_position_usage_batch(session, position_ids)
    assert usage[position_ids[0]] == (3, 2)
    assert session.execute.await_count == 2
