"""Portable metric coverage and accuracy against independently measured strings."""

import pytest

from build_key_review import load_metrics
from porta.text_metrics import TextMetrics, text_bounds


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "Hall",
        "1 square = 5 ft",
        "Élodie\u2019s library & archive",
        "Northern observation gallery",
    ],
)
def test_portable_bounds_match_recorded_ink(text: str) -> None:
    if text.isspace() or not text:
        assert text_bounds(text).width == 0
    else:
        expected = load_metrics()[text]
        actual = text_bounds(text)
        assert actual.width == pytest.approx(expected.width, abs=0.03)
        assert actual.x == pytest.approx(expected.x, abs=0.002)


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
