"""Import spine v2/v3 — forbidden import patterns for remediation teardown."""

from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN_IMPORT_PATTERNS: tuple[str, ...] = (
    r"from\s+spark\.services\.rag(\.|\s+import)",
    r"import\s+spark\.services\.rag(\.|\s)",
    r"from\s+spark\.services\.rag\.hybrid\s+import",
    r"import\s+spark\.services\.rag\.hybrid",
    r"from\s+spark\.services\.rag\.fusion_v2\s+import",
    r"from\s+spark\.ingestion\.chunking\.strategy\s+import",
    r"from\s+spark\.ingestion\.index\.sparse_encoder\s+import",
)

# v3 audit-response patterns — enforced incrementally via V3_PHASE_ENFORCED_PATTERNS.
FORBIDDEN_IMPORT_PATTERNS_V3: tuple[str, ...] = FORBIDDEN_IMPORT_PATTERNS + (
    r"from\s+spark\.retrieval\.rerank\.calibrate_scores\s+import",
    r"import\s+spark\.retrieval\.rerank\.calibrate_scores",
)

# Enforced from Phase 0 (shim re-import ban). Phase 7 adds calibrate_scores gate ban.
V3_PHASE_ENFORCED_PATTERNS: tuple[str, ...] = FORBIDDEN_IMPORT_PATTERNS + (
    r"from\s+spark\.retrieval\.rerank\.calibrate_scores\s+import",
    r"import\s+spark\.retrieval\.rerank\.calibrate_scores",
)

FORBIDDEN_IMPORT_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in FORBIDDEN_IMPORT_PATTERNS
)

FORBIDDEN_IMPORT_V3_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in FORBIDDEN_IMPORT_PATTERNS_V3
)

V3_PHASE_ENFORCED_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in V3_PHASE_ENFORCED_PATTERNS
)


@dataclass(frozen=True)
class ImportSpineViolation:
    path: str
    pattern: str
    line_number: int
    line: str


def scan_python_source(path: str, source: str) -> list[ImportSpineViolation]:
    return scan_python_source_v3(path, source, patterns=FORBIDDEN_IMPORT_PATTERNS)


def scan_python_source_v3(
    path: str,
    source: str,
    *,
    patterns: tuple[str, ...] | None = None,
) -> list[ImportSpineViolation]:
    active = patterns if patterns is not None else FORBIDDEN_IMPORT_PATTERNS_V3
    regexes = tuple(re.compile(pattern) for pattern in active)
    violations: list[ImportSpineViolation] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for regex in regexes:
            if regex.search(line):
                violations.append(
                    ImportSpineViolation(
                        path=path,
                        pattern=regex.pattern,
                        line_number=line_number,
                        line=line.strip(),
                    )
                )
    return violations
