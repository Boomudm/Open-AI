"""Bounded reading of multipart uploads.

Starlette spools large request bodies to a temp file during parsing, but a
plain ``await file.read()`` then materializes the entire body in process
memory before any size check can run — one oversized (or malicious) upload
per worker is enough to OOM the API. Every upload surface must read through
this helper so the cap is enforced while streaming.
"""

from __future__ import annotations

import io

from fastapi import HTTPException, UploadFile

_CHUNK_BYTES = 1024 * 1024


async def read_upload_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile fully, aborting with 413 once ``max_bytes`` is crossed."""
    buffer = io.BytesIO()
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        if buffer.tell() + len(chunk) > max_bytes:
            raise HTTPException(413, f"file exceeds max size of {max_bytes} bytes")
        buffer.write(chunk)
    return buffer.getvalue()
