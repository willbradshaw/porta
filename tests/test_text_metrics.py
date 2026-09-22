"""Portable metric coverage and accuracy against independently measured strings."""

import pytest

from porta.text_metrics import TextMetrics, text_bounds


# Independent full-string Inkscape measurements at 5-ft Palatino, recorded
# during visual review. No review gallery or system fonts are needed by tests.
@pytest.mark.parametrize(
    ("text", "expected_x", "expected_width"),
    [
        ("", 0, 0),
        (" ", 0, 0),
        ("Hall", 0.12, 9.3335),
        ("1 square = 5 ft", 0.305, 30.6982),
        ("Élodie\u2019s library & archive", 0.122, 56.1011),
        ("Northern observation gallery", 0.12, 64.3384),
    ],
)
def test_portable_bounds_match_recorded_ink(
    text: str, expected_x: float, expected_width: float
) -> None:
    actual = text_bounds(text)
    assert actual.width == pytest.approx(expected_width, abs=0.03)
    assert actual.x == pytest.approx(expected_x, abs=0.002)


@pytest.mark.parametrize("text", ["庭園", "🗝️", "العربية", "\u0301"])
def test_unmeasured_characters_have_finite_visible_bounds(text: str) -> None:
    bounds = text_bounds(text)
    assert bounds.width > 0
    assert bounds.height > 0


def test_combining_accents_normalize_and_metrics_cache_is_per_layout() -> None:
    assert text_bounds("E\u0301lodie") == text_bounds("Élodie")
    metrics = TextMetrics()
    assert metrics["Hall"] is metrics["Hall"]
    assert not TextMetrics()
