from __future__ import annotations

import uuid

from spark.api.v1.endpoints.ingest import _created_by_from_principal_user_id


def test_system_principal_created_by_is_null() -> None:
    assert _created_by_from_principal_user_id("00000000-0000-0000-0000-000000000000") is None


def test_uuid_principal_created_by_is_preserved() -> None:
    user_id = uuid.uuid4()

    assert _created_by_from_principal_user_id(str(user_id)) == user_id

