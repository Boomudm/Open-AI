"""Attachment download must not hold request-scoped DB session (app-layer v2 Phase 11)."""

from __future__ import annotations

import ast
from pathlib import Path


def test_stream_chat_attachment_has_no_get_session_dependency() -> None:
    source = Path("src/spark/api/v1/endpoints/chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "stream_chat_attachment":
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if isinstance(func, ast.Name) and func.id == "Depends":
                    for arg in child.args:
                        if isinstance(arg, ast.Name) and arg.id == "get_session":
                            raise AssertionError("stream_chat_attachment still Depends(get_session)")
                        if isinstance(arg, ast.Attribute) and arg.attr == "get_session":
                            raise AssertionError("stream_chat_attachment still Depends(get_session)")
            assert "AsyncSessionLocal" in source
            return
    raise AssertionError("stream_chat_attachment not found")
