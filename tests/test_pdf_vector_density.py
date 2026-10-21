"""Vector-primitive density signal — distinguishes drawing pages from text pages."""

from __future__ import annotations

from spark.ingestion.parse.pdf_vector_density import (
    PagePrimitiveDensity,
    is_vector_drawing_page,
)


def _density(**overrides: int) -> PagePrimitiveDensity:
    base = dict(page_number=1, curve_count=0, line_count=0, rect_count=0, char_count=0)
    base.update(overrides)
    return PagePrimitiveDensity(**base)


def test_dense_vector_page_with_only_title_block_text_is_flagged() -> None:
    # Real wiring_diagram.pdf shape: thousands of curves, ~400-460 chars of
    # title-block boilerplate only.
    density = _density(curve_count=2147, line_count=335, rect_count=0, char_count=415)
    assert is_vector_drawing_page(density)


def test_dense_vector_page_stays_flagged_regardless_of_primitive_volume() -> None:
    # A ratio-based check flickers page-to-page as primitive volume varies;
    # the absolute char cap must not.
    low = _density(curve_count=1167, line_count=336, rect_count=0, char_count=411)
    high = _density(curve_count=4676, line_count=8415, rect_count=0, char_count=369)
    assert is_vector_drawing_page(low)
    assert is_vector_drawing_page(high)


def test_text_heavy_page_with_a_borderless_table_is_not_flagged() -> None:
    # Real mapping_diagram.pdf shape: thousands of real characters, almost no
    # vector primitives (no ruling lines).
    density = _density(curve_count=0, line_count=0, rect_count=18, char_count=13697)
    assert not is_vector_drawing_page(density)


def test_normal_prose_page_is_not_flagged() -> None:
    density = _density(curve_count=0, line_count=0, rect_count=0, char_count=5804)
    assert not is_vector_drawing_page(density)


def test_low_primitive_count_never_triggers_even_with_little_text() -> None:
    density = _density(curve_count=10, line_count=5, rect_count=0, char_count=50)
    assert not is_vector_drawing_page(density)


def test_custom_thresholds_respected() -> None:
    density = _density(curve_count=300, line_count=0, rect_count=0, char_count=100)
    assert is_vector_drawing_page(density, curve_density_trigger=200, max_text_chars=150)
    assert not is_vector_drawing_page(density, curve_density_trigger=400, max_text_chars=150)
    assert not is_vector_drawing_page(density, curve_density_trigger=200, max_text_chars=50)
