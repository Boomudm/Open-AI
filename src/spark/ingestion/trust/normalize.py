"""Text normalization for trust rule matching."""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = re.compile(r"[\u200b-\u200d\ufeff\u2060]")
_HOMOGLYPHS = str.maketrans(
    {
        "\u0430": "a",
        "\u0435": "e",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0443": "y",
        "\u0445": "x",
        "\u0410": "A",
        "\u0415": "E",
        "\u041e": "O",
        "\u0420": "P",
        "\u0421": "C",
        "\u0423": "Y",
        "\u0425": "X",
    }
)


def normalize_policy_text(text: str) -> str:
    """NFKC normalize, fold common homoglyphs, and strip zero-width evasion chars."""
    cleaned = _ZERO_WIDTH.sub("", text or "")
    cleaned = cleaned.translate(_HOMOGLYPHS)
    return unicodedata.normalize("NFKC", cleaned)
