"""Read and validate the documented rendering defaults as one nested dictionary."""

import json
from copy import deepcopy
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any

# JSON values are checked once at load time; rendering uses their native types.
type Style = dict[str, dict[str, Any]]


def _require(condition: bool, path: str, message: str) -> None:
    """An assertion-like check that remains active under python -O."""
    if not condition:
        raise ValueError(f"{path}: {message}")


def _value(style: Style, path: str) -> Any:
    group, name = path.split(".")
    _require(group in style and name in style[group], path, "missing parameter")
    return style[group][name]


def _text(style: Style, path: str) -> str:
    value = _value(style, path)
    _require(
        isinstance(value, str) and bool(value.strip()),
        path,
        "expected a nonempty string",
    )
    return str(value)


def _number(
    style: Style,
    path: str,
    *,
    positive: bool = True,
    integer: bool = False,
    maximum: float | None = None,
) -> None:
    value = _value(style, path)
    _require(
        type(value) in (int, float) and isfinite(value),
        path,
        "expected a finite number",
    )
    if integer:
        _require(type(value) is int, path, "expected an integer")
    if positive:
        _require(value > 0, path, "expected a positive number")
    else:
        _require(value >= 0, path, "expected a nonnegative number")
    if maximum is not None:
        _require(value <= maximum, path, f"must not exceed {maximum:g}")


def _dash(style: Style, path: str) -> None:
    pattern = _text(style, path)
    try:
        lengths = [float(part) for part in pattern.replace(",", " ").split()]
    except ValueError:
        raise ValueError(f"{path}: expected a numeric dash pattern") from None
    _require(
        all(isfinite(n) and n >= 0 for n in lengths) and any(lengths),
        path,
        "dash lengths must be finite and nonnegative, with at least one positive",
    )


def _validate(style: Style) -> None:
    """Check each group explicitly, then relationships between parameters."""
    _text(style, "page.background")
    _text(style, "page.line_color")
    _number(style, "page.margin_ft", positive=False)
    _number(style, "page.display_scale")

    _text(style, "typography.font_family")
    _text(style, "typography.text_color")
    _number(style, "typography.font_weight", integer=True, maximum=1000)

    _number(style, "grid.spacing_ft", integer=True)
    _number(style, "grid.stroke_ft", positive=False)
    _number(style, "grid.opacity", positive=False, maximum=1)

    _require(
        _text(style, "labels.scheme") in ("numeric", "mnemonic"),
        "labels.scheme",
        "expected numeric or mnemonic",
    )
    _number(style, "labels.ratio", maximum=1)
    _number(style, "labels.fit", maximum=1)

    _number(style, "key.font_ft")
    _number(style, "key.identifier_gap_ft", positive=False)
    _number(style, "key.column_gap_ft", positive=False)
    _number(style, "key.line_spacing_ft")

    _number(style, "scale_bar.length_ft")
    _number(style, "scale_bar.gap_ft", positive=False)

    _number(style, "walls.interior_stroke_ft", positive=False)
    _number(style, "walls.exterior_stroke_ft", positive=False)

    _number(style, "doors.stroke_ft", positive=False)
    _dash(style, "doors.open_dash")
    _number(style, "doors.secret_font_ft")
    _number(style, "doors.secret_halo_ft", positive=False)

    _number(style, "windows.gap_ft")
    _number(style, "windows.stroke_ft", positive=False)

    _number(style, "stairs.treads_per_grid", integer=True)
    _number(style, "stairs.stroke_ft", positive=False)
    _number(style, "stairs.max_ratio", maximum=1)
    _number(style, "stairs.min_ratio", maximum=1)

    _number(style, "dividers.stroke_ft", positive=False)
    _dash(style, "dividers.dash")

    _require(
        style["key"]["line_spacing_ft"] >= style["key"]["font_ft"],
        "key.line_spacing_ft",
        "must be at least key.font_ft",
    )
    _require(
        style["stairs"]["min_ratio"] <= style["stairs"]["max_ratio"],
        "stairs.min_ratio",
        "must not exceed stairs.max_ratio",
    )


def _load_defaults() -> Style:
    definitions = json.loads(
        files("porta").joinpath("default_style.json").read_text(encoding="utf-8")
    )
    style = {
        group: {name: entry["value"] for name, entry in parameters.items()}
        for group, parameters in definitions.items()
    }
    _validate(style)
    return style


DEFAULT_STYLE = _load_defaults()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _require(name not in result, name, "duplicate key")
        result[name] = value
    return result


def _merge(style: dict[str, Any], overrides: Any, prefix: str = "") -> None:
    _require(isinstance(overrides, dict), prefix or "style", "expected a JSON object")
    for name, value in overrides.items():
        path = f"{prefix}.{name}" if prefix else name
        _require(name in style, path, "unknown style parameter")
        if isinstance(style[name], dict):
            _merge(style[name], value, path)
            continue
        if isinstance(value, dict):
            _require(
                "value" in value and not value.keys() - {"value", "description"},
                path,
                "expected value and optional description",
            )
            _require(
                "description" not in value or isinstance(value["description"], str),
                path,
                "description must be a string",
            )
            value = value["value"]
        style[name] = value


def load_style(path: str | Path) -> Style:
    """Merge a JSON file over a fresh copy of the defaults and validate it.

    Leaves may be plain values or objects with value and optional description.
    Invalid files raise ValueError; unreadable files raise OSError.
    """
    overrides = json.loads(
        Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_keys
    )
    style = deepcopy(DEFAULT_STYLE)
    _merge(style, overrides)
    _validate(style)
    return style
