"""SSE routes must not hold request-scoped DB sessions (app-layer Phase 3)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STREAM_ENDPOINTS = (
    ROOT / "src/spark/api/v1/endpoints/jobs.py",
    ROOT / "src/spark/api/v1/endpoints/chat.py",
)


def _function_has_get_session_dep(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name) and func.id == "Depends":
            for arg in child.args:
                if isinstance(arg, ast.Name) and arg.id == "get_session":
                    return True
                if isinstance(arg, ast.Attribute) and arg.attr == "get_session":
                    return True
    return False


def test_sse_route_handlers_have_no_get_session_dependency() -> None:
    violations: list[str] = []
    for path in STREAM_ENDPOINTS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "stream" not in node.name:
                continue
            if _function_has_get_session_dep(node):
                violations.append(f"{path.name}:{node.name}")
    assert not violations, f"SSE handlers still depend on get_session: {violations}"


def test_stream_generators_named_events_have_no_session_param() -> None:
  violations: list[str] = []
  for path in STREAM_ENDPOINTS:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
      if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
      if "events" not in node.name and "progress" not in node.name:
        continue
      for arg in node.args.args:
        if arg.arg == "session":
          violations.append(f"{path.name}:{node.name}")
  assert not violations, f"stream generator still accepts session: {violations}"


@pytest.mark.asyncio
async def test_subscribe_channel_yields_published_event() -> None:
    from spark.core.event_bus import INGEST_CHANNEL, publish_event, subscribe_channel

    async def _collect():
        async for payload in subscribe_channel(INGEST_CHANNEL, keepalive_sec=0.2):
            if not payload.get("__keepalive__"):
                return payload
        return None

    task = asyncio.create_task(_collect())
    await asyncio.sleep(0.05)
    await publish_event(INGEST_CHANNEL, {"job_id": "x", "status": "running"})
    result = await asyncio.wait_for(task, timeout=1.0)
    assert result is not None
    assert result.get("job_id") == "x"
