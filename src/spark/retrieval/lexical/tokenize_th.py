"""Thai tokenization for lexical index and query (PyThaiNLP newmm with fallback)."""

from __future__ import annotations

import re

_THAI_RUN_RE = re.compile(r"[\u0E00-\u0E7F]+")


def _fallback_tokenize_th(text: str) -> str:
    """Lightweight Thai split when PyThaiNLP is unavailable (tests/CI)."""
    parts: list[str] = []
    for match in _THAI_RUN_RE.finditer(text or ""):
        run = match.group(0)
        # Split on common Thai punctuation / digits embedded in runs.
        segments = re.split(r"([0-9]+|[\u0E2F\u0E46\u0E4F\u0E5A\u0E5B])", run)
        for seg in segments:
            seg = seg.strip()
            if seg and _THAI_RUN_RE.fullmatch(seg):
                parts.append(seg)
            elif seg.strip():
                parts.append(seg.strip())
    return " ".join(parts)


def tokenize_th(text: str) -> str:
    """Return space-delimited Thai tokens suitable for ``simple`` tsvector indexing."""
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        from pythainlp import word_tokenize

        tokens = word_tokenize(raw, engine="newmm", keep_whitespace=False)
        cleaned = [t.strip() for t in tokens if t and t.strip()]
        if cleaned:
            return " ".join(cleaned)
    except Exception:
        pass
    return _fallback_tokenize_th(raw)


def split_thai_latin_segments(text: str) -> tuple[str, str]:
    """Split normalized text into Thai-tokenized segment and Latin/ASCII segment."""
    normalized = (text or "").strip()
    if not normalized:
        return "", ""

    thai_parts: list[str] = []
    latin_parts: list[str] = []
    for match in re.finditer(r"[\u0E00-\u0E7F]+|[A-Za-z0-9][A-Za-z0-9._\-/]*", normalized):
        segment = match.group(0)
        if _THAI_RUN_RE.search(segment):
            thai_parts.append(segment)
        else:
            latin_parts.append(segment)
    thai_blob = tokenize_th(" ".join(thai_parts))
    latin_blob = " ".join(latin_parts).strip()
    return thai_blob, latin_blob
