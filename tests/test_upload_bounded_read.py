"""Upload size caps must be enforced while streaming — not after buffering the
whole (attacker-controlled) body in memory."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from spark.api.upload_utils import read_upload_bounded


def _upload(data: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="doc.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


async def test_reads_within_limit() -> None:
    data = b"x" * 1000
    assert await read_upload_bounded(_upload(data), 1000) == data


async def test_rejects_oversized_with_413() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await read_upload_bounded(_upload(b"x" * 1001), 1000)
    assert exc_info.value.status_code == 413


async def test_empty_upload_returns_empty_bytes() -> None:
    assert await read_upload_bounded(_upload(b""), 10) == b""
