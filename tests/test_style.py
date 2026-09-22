"""Packaged style defaults, descriptions, and validation."""

import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest

from porta.style import DEFAULT_STYLE, Style, _validate, load_style


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
        ("labels.scheme", "alphabetic", "expected numeric or mnemonic"),
        ("labels.scheme", 1, "nonempty string"),
        ("labels.scheme", "", "nonempty string"),
        ("labels.start", 0, "positive"),
        ("labels.start", -1, "positive"),
        ("labels.start", 1000, "must not exceed 999"),
        ("labels.start", 1.5, "integer"),
        ("labels.start", 1.0, "integer"),
        ("labels.start", True, "finite number"),
        ("labels.start", "10", "finite number"),
        ("labels.start", None, "finite number"),
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


@pytest.mark.parametrize(
    "overrides",
    [
        {"page": {"background": "#fff8e7"}, "grid": {"opacity": 0.4}},
        {
            "page": {"background": {"value": "#fff8e7", "description": "Paper"}},
            "grid": {"opacity": {"value": 0.4}},
        },
        {"page": {"background": "#fff8e7"}, "grid": {"opacity": {"value": 0.4}}},
    ],
    ids=["concise", "documented", "mixed"],
)
def test_style_overrides_merge_without_mutating_defaults(
    overrides: dict[str, object], tmp_path: Path
) -> None:
    before = deepcopy(DEFAULT_STYLE)
    path = tmp_path / "style.json"
    path.write_text(json.dumps(overrides))
    style = load_style(path)
    assert style["page"]["background"] == "#fff8e7"
    assert style["grid"]["opacity"] == 0.4
    assert style["grid"]["spacing_ft"] == before["grid"]["spacing_ft"]
    assert style["key"] == before["key"]
    style["key"]["font_ft"] = 99
    assert before == DEFAULT_STYLE
    assert load_style(path)["key"] == before["key"]


@pytest.mark.parametrize(
    "source",
    ["{}", '{"grid": {}}', None],
    ids=["empty", "empty-group", "documented-defaults"],
)
def test_style_defaults_round_trip(source: str | None, tmp_path: Path) -> None:
    path = tmp_path / "style.json"
    path.write_text(
        source
        if source is not None
        else files("porta").joinpath("default_style.json").read_text()
    )
    assert load_style(path) == DEFAULT_STYLE


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("[]", "JSON object"),
        ('{"unknown": {}}', "unknown style parameter"),
        ('{"page": {"unknown": 2}}', "page.unknown"),
        ('{"grid": 3}', "grid: expected a JSON object"),
        ('{"grid": {"opacity": {"description": "Missing value"}}}', "expected value"),
        ('{"grid": {"opacity": {"value": 0.5, "typo": 1}}}', "expected value"),
        (
            '{"grid": {"opacity": {"value": 0.5, "description": 2}}}',
            "description must be a string",
        ),
        ('{"grid": {"opacity": null}}', "finite number"),
        ('{"grid": {"opacity": true}}', "finite number"),
        ('{"grid": {"opacity": 1.1}}', "must not exceed"),
        ('{"grid": {"opacity": NaN}}', "finite number"),
        ('{"grid": {"opacity": 0.2, "opacity": 0.3}}', "duplicate key"),
        ('{"grid": {}, "grid": {}}', "duplicate key"),
        ('{"key": {"font_ft": 10}}', "key.line_spacing_ft"),
    ],
)
def test_bad_style_file_reports_error(
    source: str, message: str, tmp_path: Path
) -> None:
    before = deepcopy(DEFAULT_STYLE)
    path = tmp_path / "style.json"
    path.write_text(source)
    with pytest.raises(ValueError, match=message):
        load_style(path)
    assert before == DEFAULT_STYLE


@pytest.mark.parametrize("scheme", ["numeric", "mnemonic"])
@pytest.mark.parametrize("documented", [False, True], ids=["concise", "documented"])
def test_label_scheme_override(scheme: str, documented: bool, tmp_path: Path) -> None:
    path = tmp_path / "style.json"
    value = {"value": scheme} if documented else scheme
    path.write_text(json.dumps({"labels": {"scheme": value}}))
    assert load_style(path)["labels"]["scheme"] == scheme
    assert DEFAULT_STYLE["labels"]["scheme"] == "numeric"


@pytest.mark.parametrize("start", [1, 10, 999], ids=["default", "higher", "maximum"])
@pytest.mark.parametrize("documented", [False, True], ids=["concise", "documented"])
def test_numbering_start_override(start: int, documented: bool, tmp_path: Path) -> None:
    path = tmp_path / "style.json"
    value = {"value": start} if documented else start
    path.write_text(json.dumps({"labels": {"start": value}}))
    assert load_style(path)["labels"]["start"] == start
    assert DEFAULT_STYLE["labels"]["start"] == 1


@pytest.mark.parametrize("group", ["grid", "key", "scale_bar"])
@pytest.mark.parametrize(
    "value",
    [None, 0, 1, "false", [], {}],
    ids=["null", "zero", "one", "string", "array", "object"],
)
def test_visibility_requires_boolean(group: str, value: object, tmp_path: Path) -> None:
    path = tmp_path / "style.json"
    path.write_text(json.dumps({group: {"visible": value}}))
    with pytest.raises(ValueError, match=f"{group}.visible"):
        load_style(path)


@pytest.mark.parametrize(
    "value",
    [None, 0, -1, True, 2.0, "2", "AUTO", [], {}],
    ids=[
        "null",
        "zero",
        "negative",
        "boolean",
        "float",
        "numeric-string",
        "uppercase",
        "array",
        "object",
    ],
)
def test_invalid_key_columns(value: object, tmp_path: Path) -> None:
    path = tmp_path / "style.json"
    path.write_text(json.dumps({"key": {"columns": value}}))
    with pytest.raises(ValueError, match=r"key\.columns"):
        load_style(path)


@pytest.mark.parametrize("columns", ["auto", 1, 3, 1000])
@pytest.mark.parametrize("documented", [False, True], ids=["plain", "documented"])
def test_presentation_overrides(
    columns: str | int, documented: bool, tmp_path: Path
) -> None:
    overrides: Style = {
        "grid": {"visible": False},
        "key": {"visible": False, "columns": columns},
        "scale_bar": {"visible": True},
    }
    if documented:
        overrides = {
            g: {k: {"value": v} for k, v in values.items()}
            for g, values in overrides.items()
        }
    path = tmp_path / "style.json"
    path.write_text(json.dumps(overrides))
    style = load_style(path)
    assert style["key"]["columns"] == columns
    assert style["grid"]["visible"] is False
    assert style["key"]["visible"] is False
    assert style["scale_bar"]["visible"] is True
