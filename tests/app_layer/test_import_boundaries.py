"""Phase 12 — import spine guards for SSE / stream services."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STREAM_SERVICES = ROOT / "src" / "spark" / "services" / "streams"
STREAM_ENDPOINTS = (
    ROOT / "src" / "spark" / "api" / "v1" / "endpoints" / "jobs.py",
    ROOT / "src" / "spark" / "api" / "v1" / "endpoints" / "chat.py",
)


def _imports_get_session(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.endswith("database") or node.module == "spark.core.database":
                for alias in node.names:
                    if alias.name == "get_session":
                        hits.append(f"import {alias.name} from {node.module}")
    return hits


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


def test_stream_services_do_not_import_get_session() -> None:
    violations: list[str] = []
    for path in STREAM_SERVICES.glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for hit in _imports_get_session(tree):
            violations.append(f"{path.name}: {hit}")
    assert not violations, f"stream services must not import get_session: {violations}"


def test_sse_stream_handlers_do_not_depend_on_get_session() -> None:
    """Mirror Phase 3 — stream handlers must not hold request-scoped sessions."""
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


def test_web_bans_stream_consumer_shim() -> None:
    chat_lib = ROOT / "web" / "lib" / "chat"
    violations: list[str] = []
    for path in chat_lib.rglob("*.ts"):
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "stream-consumer" in text and path.name != "stream-consumer-stall.test.ts":
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"dead stream-consumer imports: {violations}"


def test_sliding_window_shim_deleted() -> None:
    """Phase 13 — rate limits use rate_limit_lua.increment_sliding_window only."""
    shim = ROOT / "src" / "spark" / "api" / "platform" / "sliding_window.py"
    assert not shim.is_file(), "delete sliding_window.py; import from rate_limit_lua"


def test_no_imports_from_sliding_window_module() -> None:
    violations: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "spark.api.platform.sliding_window" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"stale sliding_window imports: {violations}"
