"""Portable Palatino ink estimates; no system font lookup or runtime tooling.

Latin glyph advances and pair adjustments are recorded in em units. Unsupported
characters use conservative Unicode-aware widths. Viewer font substitution and
complex shaping can differ; the SVG retains editable text, not font outlines.
"""

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from unicodedata import category, east_asian_width, normalize


@dataclass(frozen=True)
class TextBounds:
    """Visible text bounds relative to its start anchor and baseline, in feet."""

    x: float
    y: float
    width: float
    height: float


@cache
def _data() -> tuple[dict[str, list[float]], dict[str, float]]:
    data = json.loads(files("porta").joinpath("palatino_metrics.json").read_text())
    return data["glyphs"], data["pairs"]


def text_bounds(text: str, size: float = 5) -> TextBounds:
    """Estimate visible ink bounds using recorded metrics and Unicode fallback."""
    glyphs, pairs = _data()
    text = normalize("NFC", text)
    position = 0.0
    boxes = []
    previous = ""
    for char in text:
        position += pairs.get(previous + char, 0)
        metric = glyphs.get(char)
        if metric is None:
            if category(char).startswith("M"):
                metric = [0, -0.3, -0.9, 0.3, 0.9]
            else:
                width = 1.1 if east_asian_width(char) in ("W", "F") else 0.7
                metric = [width, 0, -0.8, 0 if char.isspace() else width, 1]
        advance, x, y, width, height = metric
        if width:
            boxes.append((position + x, y, position + x + width, y + height))
        position += advance
        previous = char
    if not boxes:
        return TextBounds(0, 0, 0, 0)
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    return TextBounds(
        left * size,
        top * size,
        (max(b[2] for b in boxes) - left) * size,
        (max(b[3] for b in boxes) - top) * size,
    )


class TextMetrics(dict[str, TextBounds]):
    """Cache bounds for the lifetime of one layout calculation."""

    def __missing__(self, text: str) -> TextBounds:
        bounds = text_bounds(text)
        self[text] = bounds
        return bounds
