"""Structured document revision parsing for sortable version control (Phase 10)."""

from __future__ import annotations

import re
from datetime import datetime

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_DOT_RE = re.compile(r"(?i)^(?:iso[- ]?)?(\d{4})\.(\d+)$")
_REV_NUM_RE = re.compile(r"(?i)^(?:rev(?:ision)?\.?\s*|r)?(\d+)\.?$")
_REV_LETTER_RE = re.compile(r"(?i)^(?:rev(?:ision)?\.?\s*)?([A-Z])\.?$")
_V_SEMVER_RE = re.compile(r"(?i)^v(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


def parse_revision(rev: str | None) -> tuple[int, str]:
    """Return ``(sort_key, normalized_label)`` — higher sort_key means newer."""
    if not rev or not str(rev).strip():
        return 0, ""

    cleaned = str(rev).strip()
    normalized = cleaned

    date_match = _DATE_RE.match(cleaned)
    if date_match:
        year, month, day = map(int, date_match.groups())
        try:
            datetime(year, month, day)
            return year * 10_000 + month * 100 + day, normalized
        except ValueError:
            pass

    iso_match = _ISO_DOT_RE.match(cleaned)
    if iso_match:
        year = int(iso_match.group(1))
        minor = int(iso_match.group(2))
        return year * 1_000 + minor, normalized

    rev_match = _REV_NUM_RE.match(cleaned)
    if rev_match:
        number = int(rev_match.group(1))
        return number * 1_000_000, normalized

    letter_match = _REV_LETTER_RE.match(cleaned)
    if letter_match:
        letter = letter_match.group(1).upper()
        return (ord(letter) - ord("A") + 1) * 1_000_000, f"Rev {letter}"

    version_match = _V_SEMVER_RE.match(cleaned)
    if version_match:
        major = int(version_match.group(1))
        minor = int(version_match.group(2) or 0)
        patch = int(version_match.group(3) or 0)
        return major * 1_000_000 + minor * 1_000 + patch, normalized

    digits = re.findall(r"\d+", cleaned)
    if digits:
        return int(digits[-1]) * 1_000_000, normalized

    return 0, normalized


def revision_sort_key_from_label(rev: str | None) -> int | None:
    if not rev or not str(rev).strip():
        return None
    sort_key, _ = parse_revision(rev)
    return sort_key if sort_key > 0 else None
