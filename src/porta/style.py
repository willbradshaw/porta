"""Documented SVG defaults loaded from the packaged JSON resource."""

import json
from dataclasses import dataclass, fields
from importlib.resources import files
from math import isfinite

_DEFINITIONS = json.loads(
    files("porta").joinpath("default_style.json").read_text(encoding="utf-8")
)


# Public JSON paths map to the renderer's resolved parameter names.
_PATHS = {
    "background": "page.background",
    "margin_ft": "page.margin_ft",
    "display_scale": "page.display_scale",
    "line_color": "page.line_color",
    "font_family": "typography.font_family",
    "font_weight": "typography.font_weight",
    "text_color": "typography.text_color",
    "grid_ft": "grid.spacing_ft",
    "grid_opacity": "grid.opacity",
    "grid_stroke_ft": "grid.stroke_ft",
    "label_ratio": "labels.ratio",
    "label_fit": "labels.fit",
    "key_font_ft": "key.font_ft",
    "key_gap_ft": "key.identifier_gap_ft",
    "column_gap_ft": "key.column_gap_ft",
    "key_line_spacing_ft": "key.line_spacing_ft",
    "scale_gap_ft": "scale_bar.gap_ft",
    "scale_length_ft": "scale_bar.length_ft",
    "wall_stroke_ft": "walls.interior_stroke_ft",
    "exterior_wall_stroke_ft": "walls.exterior_stroke_ft",
    "door_stroke_ft": "doors.stroke_ft",
    "open_dash": "doors.open_dash",
    "secret_font_ft": "doors.secret_font_ft",
    "secret_halo_ft": "doors.secret_halo_ft",
    "window_gap_ft": "windows.gap_ft",
    "window_stroke_ft": "windows.stroke_ft",
    "treads_per_grid": "stairs.treads_per_grid",
    "tread_stroke_ft": "stairs.stroke_ft",
    "tread_max_ratio": "stairs.max_ratio",
    "tread_min_ratio": "stairs.min_ratio",
    "divider_stroke_ft": "dividers.stroke_ft",
    "divider_dash": "dividers.dash",
}
_LEAVES = {
    name: _DEFINITIONS[group][key]
    for name, path in _PATHS.items()
    for group, key in [path.split(".")]
}


@dataclass(frozen=True)
class Style:
    """Resolved SVG parameters; descriptions and defaults live in default_style.json."""

    grid_ft: int
    margin_ft: float
    wall_stroke_ft: float
    exterior_wall_stroke_ft: float
    label_ratio: float
    label_fit: float
    font_family: str
    text_color: str
    key_font_ft: float
    scale_gap_ft: float
    scale_length_ft: float
    key_gap_ft: float
    column_gap_ft: float
    key_line_spacing_ft: float
    grid_opacity: float
    grid_stroke_ft: float
    door_stroke_ft: float
    open_dash: str
    secret_font_ft: float
    secret_halo_ft: float
    treads_per_grid: int
    tread_stroke_ft: float
    tread_max_ratio: float
    tread_min_ratio: float
    divider_stroke_ft: float
    divider_dash: str
    display_scale: float
    background: str
    line_color: str
    window_gap_ft: float
    window_stroke_ft: float
    font_weight: int

    @property
    def scale_font_ft(self) -> float:
        """Derive scale proportions from the shared key/scale text size."""
        return self.key_font_ft

    @property
    def scale_height_ft(self) -> float:
        """Derive scale proportions from the shared key/scale text size."""
        return self.key_font_ft * 0.3

    @property
    def scale_stroke_ft(self) -> float:
        """Derive scale proportions from the shared key/scale text size."""
        return self.key_font_ft * 0.04

    @property
    def scale_caption_offset_ft(self) -> float:
        """Derive scale proportions from the shared key/scale text size."""
        return self.key_font_ft * 1.2

    @property
    def scale_label_offset_ft(self) -> float:
        """Derive scale proportions from the shared key/scale text size."""
        return self.key_font_ft * -0.6

    def __post_init__(self) -> None:
        for field in fields(self):
            name = field.name
            value = getattr(self, name)
            label = _PATHS[name]
            default = _LEAVES[name]["value"]
            if isinstance(default, str):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{label}: expected a nonempty string")
                if name.endswith("_dash"):
                    try:
                        lengths = [
                            float(part) for part in value.replace(",", " ").split()
                        ]
                    except ValueError:
                        raise ValueError(
                            f"{label}: expected a numeric dash pattern"
                        ) from None
                    if not all(isfinite(n) and n >= 0 for n in lengths) or not any(
                        lengths
                    ):
                        raise ValueError(
                            f"{label}: dash lengths must be finite and nonnegative; "
                            "at least one must be positive"
                        )
                continue
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"{label}: expected a finite number")
            if (
                name in {"grid_ft", "treads_per_grid", "font_weight"}
                and type(value) is not int
            ):
                raise ValueError(f"{label}: expected an integer")
            zero_allowed = name.endswith("_stroke_ft") or name in {
                "grid_opacity",
                "margin_ft",
                "key_gap_ft",
                "column_gap_ft",
                "secret_halo_ft",
                "scale_gap_ft",
            }
            if value < 0 or (value == 0 and not zero_allowed):
                kind = "nonnegative" if zero_allowed else "positive"
                raise ValueError(f"{label}: expected a {kind} number")
            if (
                name
                in {"label_ratio", "label_fit", "tread_min_ratio", "tread_max_ratio"}
                and value > 1
            ):
                raise ValueError(f"{label}: expected a fraction no greater than 1")
            if name == "grid_opacity" and value > 1:
                raise ValueError("grid.opacity: must be between 0 and 1")
            if name == "font_weight" and value > 1000:
                raise ValueError(
                    "typography.font_weight: expected an integer from 1 to 1000"
                )

        if self.key_line_spacing_ft < self.key_font_ft:
            raise ValueError("key.line_spacing_ft must be at least key.font_ft")
        if self.tread_min_ratio > self.tread_max_ratio:
            raise ValueError("stairs.min_ratio must not exceed stairs.max_ratio")


DEFAULT_STYLE = Style(**{name: entry["value"] for name, entry in _LEAVES.items()})
