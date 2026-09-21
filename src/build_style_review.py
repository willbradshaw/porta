#!/usr/bin/env -S uv run python
"""Generate the bounded #99 visual review, including a frozen before rendering.

Run from the repository root. The HTML embeds all SVGs and can be opened offline.
It intentionally retains the original baseline; it is not a golden test updater.
"""

import base64
import subprocess
import types
from pathlib import Path

from porta.layout import solve
from porta.parser import parse
from porta.render import render_svg

_BASELINE = "9fc5e2644b30c478d95b5968806be813295359b1"
_OUT = Path("docs/style-review")


def main() -> None:
    """Write reproducible before/after compositions for review."""
    old = types.ModuleType("porta_style_baseline")
    source = subprocess.check_output(
        ["git", "show", f"{_BASELINE}:src/porta/render.py"], text=True
    )
    exec(compile(source, "baseline/render.py", "exec"), old.__dict__)
    cases = {
        "tiny": 'room a "Store" 5x5 root glyph="1"',
        "manor": Path("examples/manor.porta").read_text(),
        "corridor": Path("tests/fixtures/layouts/corridor.porta").read_text(),
        "block": Path("tests/fixtures/layouts/block.porta").read_text(),
        "outdoors": Path(
            "tests/fixtures/layouts/exterior-door-kinds.porta"
        ).read_text(),
        "components": Path("tests/fixtures/layouts/components-row.porta").read_text(),
        "features": (_OUT / "features.porta").read_text(),
        "labels": (_OUT / "labels.porta").read_text(),
        "unlabeled": 'room a "" 10x10 root glyph=""',
    }
    rooms = []
    for i in range(42):
        placement = (
            "root"
            if i == 0
            else (f"down-of r{i - 7}" if i % 7 == 0 else f"right-of r{i - 1}")
        )
        rooms.append(f'room r{i} "Room {i + 1}" 20x15 {placement} glyph="{i + 1}"')
    cases["large-key"] = "\n".join(rooms)
    html = [
        """<!doctype html><meta charset="utf-8"><title>Porta visual review</title>
<style>
body {font: 15px Arial,sans-serif; margin:24px; color:#222}
section {break-before:page; margin-bottom:40px}
.comparison {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px}
figure {margin:0} figcaption {margin:8px 0} img {width:100%; height:auto}
.refinements img {max-height:520px; object-fit:contain; object-position:top}
@page {size:A4; margin:10mm}
@media print {
  .comparison {display:block} .before,.refinements {display:none}
  section {margin:0} img {width:190mm; max-height:245mm; object-fit:contain}
  section.tiny img,section.unlabeled img {width:80mm}
}
</style><h1>Default SVG design review</h1>
<p>Before / chosen default. Open at 1280px or wider; print on A4 at 100%.
Print uses one chosen composition per page, up to 190mm wide (tiny: 80mm).
All images are embedded and require no network.</p>"""
    ]
    for name, spec in cases.items():
        building = solve(parse(spec))
        before = old.render_svg(building)
        after = render_svg(building)
        (_OUT / f"{name}-before.svg").write_text(before)
        (_OUT / f"{name}-after.svg").write_text(after)
        html.append(f'<section class="{name}"><h2>{name}</h2><div class="comparison">')
        for label, svg in (("Before", before), ("Chosen default", after)):
            data = base64.b64encode(svg.encode()).decode()
            css = "before" if label == "Before" else "after"
            html.append(
                f'<figure class="{css}"><figcaption>{label}</figcaption>'
                f'<img alt="{name}: {label}" src="data:image/svg+xml;base64,{data}">'
                "</figure>"
            )
        html.append("</div></section>")
    (_OUT / "index.html").write_text("\n".join(html))


if __name__ == "__main__":
    main()
