import pytest

from fastapi import HTTPException

from spark.retrieval.safety.rate_limit import check_rag_query_rate_limit


@pytest.mark.asyncio
async def test_rag_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spark.retrieval.safety.rate_limit.settings.rag_query_rate_limit_per_user_min",
        1,
    )
    monkeypatch.setattr(
        "spark.retrieval.safety.rate_limit.settings.rag_query_rate_limit_per_factory_min",
        0,
    )
    await check_rag_query_rate_limit(user_id="user-1", factory_id="F-01")
    with pytest.raises(HTTPException) as exc:
        await check_rag_query_rate_limit(user_id="user-1", factory_id="F-01")
    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "60"
