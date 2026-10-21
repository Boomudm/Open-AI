"""Public API docs surfaces stay unauthenticated and renderable."""

from __future__ import annotations

from spark.api.platform.middleware.security_headers import _csp_for_path
from spark.core.security import _is_public


def test_docs_paths_are_public() -> None:
    assert _is_public("/docs")
    assert _is_public("/docs/oauth2-redirect")
    assert _is_public("/redoc")
    assert _is_public("/openapi.json")


def test_docs_csp_allows_swagger_cdn() -> None:
    docs_csp = _csp_for_path("/docs")
    assert "cdn.jsdelivr.net" in docs_csp
    assert "unsafe-inline" in docs_csp
    # Default API CSP stays tight.
    assert "cdn.jsdelivr.net" not in _csp_for_path("/api/v1/auth/login")
    assert _csp_for_path("/healthz").startswith("default-src 'self'")


def test_redoc_uses_pinned_jsdelivr_bundle() -> None:
    """FastAPI's default redoc@next CDN 404s — we pin a working redoc@2.x URL."""
    from fastapi.openapi.docs import get_redoc_html

    html = get_redoc_html(
        openapi_url="/openapi.json",
        title="Neo Chat API - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    ).body.decode()
    assert "redoc@2.1.5/bundles/redoc.standalone.js" in html
    assert "redoc@next" not in html

    # Guard the live wiring in main.py (avoid importing app — production validators).
    from pathlib import Path

    main_src = Path(__file__).resolve().parents[1] / "src/spark/main.py"
    text = main_src.read_text()
    assert "redoc_url=None" in text
    assert "redoc@2.1.5/bundles/redoc.standalone.js" in text
    assert 'redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next' not in text
