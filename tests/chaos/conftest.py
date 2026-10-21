"""Chaos engineering tests — excluded from default CI via pytest marker."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "chaos: chaos engineering / soak tests (run in nightly-chaos-v3 and pre-cutover gate)",
    )
