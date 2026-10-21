"""Wire-topology graph extraction from vector-drawing PDF pages (Fix C, Phase 1).

Feasibility spike (see docs/internal — Phase 0) against the real 14-page
``wiring_diagram.pdf`` found two things:

1. Endpoint-clustering ``page.lines`` DOES recover real wire runs between
   component terminals with good precision — verified by hand against the
   rendered page (e.g. a QM4 contact -> "+24VDC" wire -> Battery terminal
   chain matched the diagram exactly).
2. Naive clustering over *all* lines also picks up component-symbol interior
   strokes (contactor icon bars, vectorized text glyphs) as spurious tiny
   "chains", because those symbols are drawn partly with straight ``line``
   primitives, not exclusively ``curve`` primitives as first assumed. On the
   real file, line lengths are sharply bimodal: 89% of lines are under 10pt
   (symbol/glyph strokes) while real wire runs and sheet borders are 20pt+
   (measured: page 5 of wiring_diagram.pdf, n=470, buckets
   [0,10)=418, [20,80)=21, [80,1000)=11). A length filter cleanly separates
   the two populations.

This module does NOT attempt label attachment (Phase 2 — which chain
endpoint belongs to which component/terminal) or cross-sheet bus continuity
(wires that continue onto another page via a matching net label rather than
a drawn line) — both remain open and are the harder, unverified part of
wiring-diagram connectivity tracing. Nodes here are anonymous coordinates;
pairing them with a human-readable tag is future work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_MIN_WIRE_LENGTH = 15.0
DEFAULT_ENDPOINT_TOLERANCE = 1.5


@dataclass(frozen=True)
class WireSegment:
    index: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass(frozen=True)
class WireChain:
    """A connected run of wire-like segments sharing endpoints."""

    segment_indices: tuple[int, ...]
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)


def _snap(point: tuple[float, float], tolerance: float) -> tuple[float, float]:
    return (round(point[0] / tolerance) * tolerance, round(point[1] / tolerance) * tolerance)


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[Any, Any] = {}

    def find(self, x: Any) -> Any:
        self._parent.setdefault(x, x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: Any, b: Any) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def wire_like_segments(
    raw_lines: list[dict[str, float]],
    *,
    min_wire_length: float = DEFAULT_MIN_WIRE_LENGTH,
) -> list[WireSegment]:
    """Filter ``pdfplumber`` page.lines down to plausible wire runs.

    Drops short strokes that belong to component-symbol interiors or
    vectorized text glyphs rather than an actual wire between terminals.
    """
    segments = [
        WireSegment(index=i, x0=line["x0"], y0=line["y0"], x1=line["x1"], y1=line["y1"])
        for i, line in enumerate(raw_lines)
    ]
    return [s for s in segments if s.length >= min_wire_length]


def build_wire_chains(
    segments: list[WireSegment],
    *,
    endpoint_tolerance: float = DEFAULT_ENDPOINT_TOLERANCE,
) -> list[WireChain]:
    """Group wire-like segments into chains by shared (snapped) endpoints."""
    uf = _UnionFind()
    for seg in segments:
        a = _snap((seg.x0, seg.y0), endpoint_tolerance)
        b = _snap((seg.x1, seg.y1), endpoint_tolerance)
        uf.union(a, b)

    groups: dict[Any, list[WireSegment]] = {}
    for seg in segments:
        root = uf.find(_snap((seg.x0, seg.y0), endpoint_tolerance))
        groups.setdefault(root, []).append(seg)

    chains: list[WireChain] = []
    for group in groups.values():
        xs = [s.x0 for s in group] + [s.x1 for s in group]
        ys = [s.y0 for s in group] + [s.y1 for s in group]
        chains.append(
            WireChain(
                segment_indices=tuple(s.index for s in group),
                bbox=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return chains


def extract_wire_chains_for_page(
    pdf_path: Path,
    page_number: int,
    *,
    min_wire_length: float = DEFAULT_MIN_WIRE_LENGTH,
    endpoint_tolerance: float = DEFAULT_ENDPOINT_TOLERANCE,
) -> list[WireChain]:
    """Best-effort: returns [] if pdfplumber can't open the file (never raises)."""
    try:
        import pdfplumber
    except ImportError:
        return []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            page = pdf.pages[page_number - 1]
            segments = wire_like_segments(list(page.lines), min_wire_length=min_wire_length)
    except Exception as exc:  # noqa: BLE001 — best-effort, never blocks ingestion
        log.warning(
            "schematic_graph_extract_failed",
            file=str(pdf_path),
            page=page_number,
            error=str(exc)[:200],
        )
        return []
    return build_wire_chains(segments, endpoint_tolerance=endpoint_tolerance)
