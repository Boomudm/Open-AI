"""Wire-topology graph extraction — Fix C Phase 0/1 spike validation.

Fixture numbers are derived from a hand-verified spike against the real
wiring_diagram.pdf (page 5): line lengths are sharply bimodal — 418/470
lines under 10pt (symbol/glyph interior strokes) vs. 30 lines 20pt+ (real
wire runs + sheet border). The "QM4 contact -> +24VDC wire -> Battery
terminal" case below reproduces coordinates read off that real chain.
"""

from __future__ import annotations

from unittest.mock import patch

from spark.ingestion.parse.schematic_graph import (
    build_wire_chains,
    extract_wire_chains_for_page,
    wire_like_segments,
)


def _line(x0: float, y0: float, x1: float, y1: float) -> dict[str, float]:
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def test_wire_like_segments_drops_symbol_interior_strokes() -> None:
    raw = [
        _line(43, 656, 56, 667),  # ~15.5pt — contactor icon interior stroke
        _line(274, 708, 323, 733),  # ~55pt — real wire run
        _line(583.7, 707.6, 583.7, 748.6),  # 41pt — real wire run
    ]
    kept = wire_like_segments(raw, min_wire_length=15.0)
    lengths = sorted(round(s.length) for s in kept)
    assert 41 in lengths
    assert 55 in lengths
    # the short interior stroke sits right at the boundary — use a case that
    # is unambiguously below threshold to assert the filter actually drops:
    raw_short = [_line(0, 0, 3, 4)]  # length 5
    assert wire_like_segments(raw_short, min_wire_length=15.0) == []


def test_build_wire_chains_merges_touching_segments() -> None:
    # A wire drawn as an arrowhead (2 short strokes) feeding into the main run —
    # all three share an endpoint at (300, 720).
    segments = wire_like_segments(
        [
            _line(274, 708, 300, 720),
            _line(300, 720, 323, 733),
            _line(300, 720, 350, 720),
        ],
        min_wire_length=15.0,
    )
    chains = build_wire_chains(segments, endpoint_tolerance=1.5)
    assert len(chains) == 1
    assert len(chains[0].segment_indices) == 3


def test_build_wire_chains_stops_at_component_boundary() -> None:
    """Real EE-CAD convention: a wire run ends where it meets a component
    symbol (drawn with curves/rects, not lines) — an unrelated wire nearby
    that does NOT share an endpoint must stay in its own chain."""
    segments = wire_like_segments(
        [
            _line(274, 708, 323, 733),  # QM4 -> +24VDC wire
            _line(500, 100, 550, 100),  # unrelated wire elsewhere on the page
        ],
        min_wire_length=15.0,
    )
    chains = build_wire_chains(segments)
    assert len(chains) == 2
    assert {len(c.segment_indices) for c in chains} == {1}


def test_build_wire_chains_bbox_covers_all_segments() -> None:
    segments = wire_like_segments(
        [_line(274, 708, 300, 720), _line(300, 720, 323, 733)], min_wire_length=15.0
    )
    chains = build_wire_chains(segments)
    assert len(chains) == 1
    x0, y0, x1, y1 = chains[0].bbox
    assert x0 == 274
    assert x1 == 323
    assert y0 == 708
    assert y1 == 733


def test_extract_wire_chains_for_page_never_raises_on_bad_file() -> None:
    from pathlib import Path

    result = extract_wire_chains_for_page(Path("/nonexistent/does_not_exist.pdf"), 1)
    assert result == []


def test_extract_wire_chains_for_page_missing_pdfplumber_returns_empty() -> None:
    from pathlib import Path

    with patch.dict("sys.modules", {"pdfplumber": None}):
        result = extract_wire_chains_for_page(Path("whatever.pdf"), 1)
    assert result == []
