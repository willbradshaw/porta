"""Packaged style defaults, descriptions, and validation."""

import json
from copy import deepcopy
from importlib.resources import files

import pytest

from porta.style import DEFAULT_STYLE, _validate


def test_documented_defaults_cover_resolved_parameters() -> None:
    definitions = json.loads(files("porta").joinpath("default_style.json").read_text())
    assert {
        group: {name: entry["value"] for name, entry in parameters.items()}
        for group, parameters in definitions.items()
    } == DEFAULT_STYLE
    assert all(
        entry["description"].strip()
        for group in definitions.values()
        for entry in group.values()
    )


@pytest.mark.parametrize("opacity", [0, 0.23, 1])
def test_grid_opacity_range(opacity: float) -> None:
    style = deepcopy(DEFAULT_STYLE)
    style["grid"]["opacity"] = opacity
    _validate(style)


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("grid.opacity", -0.1, "grid.opacity"),
        ("grid.opacity", 1.1, "grid.opacity"),
        ("grid.opacity", True, "finite number"),
        ("grid.opacity", "0.23", "finite number"),
        ("key.font_ft", 0, "positive"),
        ("grid.spacing_ft", 2.5, "integer"),
        ("page.margin_ft", -1, "nonnegative"),
        ("page.display_scale", float("inf"), "finite number"),
        ("scale_bar.length_ft", float("nan"), "finite number"),
        ("typography.font_family", "", "nonempty string"),
        ("doors.open_dash", "a b", "numeric dash"),
        ("dividers.dash", "0 0", "dash lengths"),
        ("stairs.min_ratio", 0.9, "must not exceed"),
        ("labels.fit", 2, "must not exceed 1"),
        ("typography.font_weight", 1001, "must not exceed 1000"),
        ("key.line_spacing_ft", 0.5, "at least key.font_ft"),
    ],
)
def test_invalid_default_values(parameter: str, value: object, message: str) -> None:
    values = deepcopy(DEFAULT_STYLE)
    group, name = parameter.split(".")
    values[group][name] = value
    with pytest.raises(ValueError, match=message):
        _validate(values)


@pytest.mark.parametrize("group", list(DEFAULT_STYLE))
def test_missing_default_group_reports_its_path(group: str) -> None:
    style = deepcopy(DEFAULT_STYLE)
    del style[group]
    with pytest.raises(ValueError, match=rf"{group}\..*: missing parameter"):
        _validate(style)
