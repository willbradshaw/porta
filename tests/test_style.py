"""Packaged style defaults, descriptions, and validation."""

import json
from dataclasses import asdict, replace
from importlib.resources import files

import pytest

from porta.style import DEFAULT_STYLE, Style


def test_documented_defaults_cover_resolved_parameters() -> None:
    definitions = json.loads(files("porta").joinpath("default_style.json").read_text())
    leaves = [entry for group in definitions.values() for entry in group.values()]
    assert len(leaves) == len(asdict(DEFAULT_STYLE))
    assert all(entry["description"].strip() for entry in leaves)
    assert DEFAULT_STYLE.background == definitions["page"]["background"]["value"]
    assert DEFAULT_STYLE.grid_opacity == definitions["grid"]["opacity"]["value"]


@pytest.mark.parametrize("opacity", [0, 0.23, 1])
def test_grid_opacity_range(opacity: float) -> None:
    assert replace(DEFAULT_STYLE, grid_opacity=opacity).grid_opacity == opacity


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("grid_opacity", -0.1, "grid.opacity"),
        ("grid_opacity", 1.1, "grid.opacity"),
        ("grid_opacity", True, "finite number"),
        ("grid_opacity", "0.23", "finite number"),
        ("key_font_ft", 0, "positive"),
        ("grid_ft", 2.5, "integer"),
        ("margin_ft", -1, "nonnegative"),
        ("display_scale", float("inf"), "finite number"),
        ("scale_length_ft", float("nan"), "finite number"),
        ("font_family", "", "nonempty string"),
        ("open_dash", "a b", "numeric dash"),
        ("divider_dash", "0 0", "dash lengths"),
        ("tread_min_ratio", 0.9, "must not exceed"),
        ("label_fit", 2, "fraction"),
        ("font_weight", 1001, "1 to 1000"),
        ("key_line_spacing_ft", 0.5, "at least key.font_ft"),
    ],
)
def test_invalid_default_values(parameter: str, value: object, message: str) -> None:
    values = asdict(DEFAULT_STYLE)
    values[parameter] = value
    with pytest.raises(ValueError, match=message):
        Style(**values)
