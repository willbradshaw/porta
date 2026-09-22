"""Read and validate the documented SVG defaults as one nested dictionary."""

import json
from importlib.resources import files
from math import isfinite
from typing import Any

# JSON values are checked once at load time; rendering uses their native types.
type Style = dict[str, dict[str, Any]]


def _validate(style: Style) -> None:
    for group, parameters in style.items():
        for name, value in parameters.items():
            path = f"{group}.{name}"
            is_string = name.endswith("color") or path in {
                "page.background",
                "typography.font_family",
                "doors.open_dash",
                "dividers.dash",
            }
            if is_string:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{path}: expected a nonempty string")
                if name.endswith("dash"):
                    try:
                        lengths = [
                            float(part) for part in value.replace(",", " ").split()
                        ]
                    except ValueError:
                        raise ValueError(
                            f"{path}: expected a numeric dash pattern"
                        ) from None
                    if not all(isfinite(n) and n >= 0 for n in lengths) or not any(
                        lengths
                    ):
                        raise ValueError(
                            f"{path}: dash lengths must be nonnegative and finite, "
                            "with at least one positive"
                        )
                continue
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"{path}: expected a finite number")
            if (
                path
                in {
                    "grid.spacing_ft",
                    "stairs.treads_per_grid",
                    "typography.font_weight",
                }
                and type(value) is not int
            ):
                raise ValueError(f"{path}: expected an integer")
            zero_allowed = name.endswith("stroke_ft") or path in {
                "grid.opacity",
                "page.margin_ft",
                "key.identifier_gap_ft",
                "key.column_gap_ft",
                "doors.secret_halo_ft",
                "scale_bar.gap_ft",
            }
            if value < 0 or (value == 0 and not zero_allowed):
                kind = "nonnegative" if zero_allowed else "positive"
                raise ValueError(f"{path}: expected a {kind} number")
            if (
                path
                in {
                    "labels.ratio",
                    "labels.fit",
                    "stairs.min_ratio",
                    "stairs.max_ratio",
                }
                and value > 1
            ):
                raise ValueError(f"{path}: expected a fraction no greater than 1")
            if path == "grid.opacity" and value > 1:
                raise ValueError("grid.opacity: must be between 0 and 1")
            if path == "typography.font_weight" and value > 1000:
                raise ValueError(
                    "typography.font_weight: expected an integer from 1 to 1000"
                )
    if style["key"]["line_spacing_ft"] < style["key"]["font_ft"]:
        raise ValueError("key.line_spacing_ft must be at least key.font_ft")
    if style["stairs"]["min_ratio"] > style["stairs"]["max_ratio"]:
        raise ValueError("stairs.min_ratio must not exceed stairs.max_ratio")


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
