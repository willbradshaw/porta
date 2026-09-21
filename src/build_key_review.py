#!/usr/bin/env -S uv run python
"""Compare the production key with independently measured Palatino layouts.

Run from the repository root. Both paths use the approved scoring algorithm;
only the metrics differ. Inkscape is optional development tooling, not runtime.
"""

import argparse
import json
import subprocess
import tempfile
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

from porta import render
from porta.key_layout import (
    Candidate,
    choose_layout,
    interword_breaks,
    text_fragments,
)
from porta.layout import solve
from porta.model import Building
from porta.parser import parse
from porta.text_metrics import TextBounds, TextMetrics

_INPUT = Path("tests/fixtures/key-layouts")
_OUTPUT = Path("docs/style-review/key-layouts")
_NS = "http://www.w3.org/2000/svg"
_FONT = 5.0
_LINE = 8.0
_MARGIN = 10.0
_GLYPH_GAP = 2.0
_COLUMN_GAP = 6.0
_WORD_SPLIT_PENALTY = 0.5
_HEIGHT_COEFFICIENT = 0.7
_INTERWORD_PENALTY = 0.1
_METRICS = _OUTPUT / "palatino-text-bounds.json"


def measure_texts(texts: set[str], inkscape: str) -> None:
    """Cache actual SVG text bounds using Inkscape (a review-only dependency)."""
    strings = sorted(texts - {""})
    root = ET.Element(
        f"{{{_NS}}}svg",
        {
            "width": "2000",
            "height": str((len(strings) + 1) * 20),
            "font-family": render._FONT_FAMILY,
            "font-size": str(_FONT),
            "font-weight": "400",
        },
    )
    for i, text in enumerate(strings):
        ET.SubElement(
            root,
            f"{{{_NS}}}text",
            {
                "id": f"measure-{i}",
                "x": "100",
                "y": str(i * 20 + 10),
            },
        ).text = text
    ET.register_namespace("", _NS)
    with tempfile.TemporaryDirectory(prefix="porta-text-metrics-") as directory:
        path = Path(directory) / "measure.svg"
        path.write_text(ET.tostring(root, encoding="unicode"))
        output = subprocess.check_output(
            [inkscape, str(path), "--query-all"], text=True
        )
    values = {"": [0.0, 0.0, 0.0, 0.0]}
    for line in output.splitlines():
        identifier, *numbers = line.split(",")
        if not identifier.startswith("measure-"):
            continue
        i = int(identifier.removeprefix("measure-"))
        x, y, width, height = map(float, numbers)
        values[strings[i]] = [
            round(x - 100, 6),
            round(y - (i * 20 + 10), 6),
            width,
            height,
        ]
    if set(values) != set(strings) | {""}:
        raise ValueError("Inkscape did not return all requested text bounds")
    _METRICS.write_text(
        json.dumps(
            {
                "font_family": render._FONT_FAMILY,
                "font_size": _FONT,
                "renderer": subprocess.check_output(
                    [inkscape, "--version"], text=True
                ).strip(),
                "bounds": values,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def load_metrics() -> dict[str, TextBounds]:
    """Load recorded font measurements; never silently use width estimates."""
    data = json.loads(_METRICS.read_text())
    if data["font_family"] != render._FONT_FAMILY or data["font_size"] != _FONT:
        raise ValueError("Font changed; rerun with --measure /path/to/inkscape")
    return {text: TextBounds(*bounds) for text, bounds in data["bounds"].items()}


def _entries(building: Building) -> list[tuple[str, str]]:
    """Use the renderer's unchanged glyph assignment and key ordering."""
    glyphs = render._assign_glyphs(building)
    by_id = {room.id: room for room in building.rooms}
    return [
        (glyphs[eid], render._key_name(building, by_id, eid))
        for eid in render._legend_ids(building, render._member_block(building), glyphs)
    ]


def _review_svg(
    building: Building, candidate: Candidate, metrics: dict[str, TextBounds]
) -> str:
    """Retain map geometry and replace all furniture with the review layout."""
    root = ET.fromstring(render.render_svg(building))
    root.set("fill", "black")
    for node in list(root):
        if node.get("class") in ("scale", "key"):
            root.remove(node)
    xs = [room.x for room in building.rooms]
    ys = [room.y for room in building.rooms]
    assert all(x is not None for x in xs)
    assert all(y is not None for y in ys)
    min_x = min(x for x in xs if x is not None)
    min_y = min(y for y in ys if y is not None)
    max_x = max(room.x + room.width for room in building.rooms if room.x is not None)
    max_y = max(room.y + room.height for room in building.rooms if room.y is not None)
    center = (min_x + max_x) / 2
    caption = "1 square = 5 ft"
    caption_y = max_y + _MARGIN + _FONT
    key_y = caption_y + 2 * _LINE
    width = max(max_x - min_x, candidate.width, metrics[caption].width) + 2 * _MARGIN
    bottom = key_y + (candidate.lines - 1) * _LINE + _FONT * 0.3 + _MARGIN
    x, y, height = center - width / 2, min_y - _MARGIN, bottom - min_y + _MARGIN
    root.set("viewBox", f"{x:g} {y:g} {width:g} {height:g}")
    root.set("width", f"{width * 10:g}")
    root.set("height", f"{height * 10:g}")
    background = root.find("{*}rect")
    assert background is not None
    for key, value in (("x", x), ("y", y), ("width", width), ("height", height)):
        background.set(key, f"{value:g}")
    ET.SubElement(
        root,
        f"{{{_NS}}}text",
        {
            "class": "scale",
            "font-size": str(_FONT),
            "x": str(center - metrics[caption].width / 2 - metrics[caption].x),
            "y": str(caption_y),
        },
    ).text = caption
    left = center - candidate.width / 2 - candidate.left_trim
    for column, column_width, glyph_width in zip(
        candidate.columns, candidate.widths, candidate.glyph_widths, strict=True
    ):
        row = 0
        for glyph, name in column:
            group = ET.SubElement(
                root, f"{{{_NS}}}g", {"class": "key", "font-size": str(_FONT)}
            )
            attrs = {
                "x": str(left + glyph_width - metrics[glyph].width - metrics[glyph].x),
                "y": str(key_y + row * _LINE),
            }
            ET.SubElement(group, f"{{{_NS}}}text", attrs).text = glyph
            for line_index, line in enumerate(candidate.rows[name]):
                attrs = {
                    "x": str(left + glyph_width + _GLYPH_GAP - metrics[line].x),
                    "y": str(key_y + (row + line_index) * _LINE),
                }
                ET.SubElement(group, f"{{{_NS}}}text", attrs).text = line
            row += max(1, len(candidate.rows[name]))
        left += column_width + _COLUMN_GAP
    ET.register_namespace("", _NS)
    return ET.tostring(root, encoding="unicode")


def main() -> None:
    """Write paired SVGs, every candidate's score, and an offline review index."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check without writing")
    parser.add_argument(
        "--measure", metavar="INKSCAPE", help="refresh cached text bounds"
    )
    parser.add_argument("--export-png", metavar="INKSCAPE", help="export review PNGs")
    args = parser.parse_args()
    if (args.measure or args.export_png) and args.check:
        parser.error(
            "--measure/--export-png write files and cannot be combined with --check"
        )
    if args.measure:
        texts = {"1 square = 5 ft"}
        for path in sorted(_INPUT.glob("*.porta")):
            for glyph, name in _entries(solve(parse(path.read_text()))):
                texts.add(glyph)
                texts.update(text_fragments(name))
        measure_texts(texts, args.measure)
    metrics = load_metrics()
    outputs: dict[Path, str] = {}
    html = [
        '<!doctype html><meta charset="utf-8"><title>Production key review</title>',
        "<style>body{font:16px sans-serif;margin:24px}.pair{display:flex;gap:20px}"
        "figure{flex:1;margin:0}img{width:100%}</style>",
        "<h1>Production key layouts</h1>",
        "<p>B = 0.7((L - 4)/4)² + ((W - T)/T)² + 0.5S + 0.1R. "
        "T = max(map width, scale-line width). S counts internal-word breaks; "
        "R counts between-word breaks. Equal-width columns.</p>",
        "<p>Recorded Inkscape bounds on the left; portable production metrics "
        "on the right. Both use the same search and score. "
        "Full-size production PNGs are available with --export-png.</p>",
    ]
    report = [
        "# Approved production key layouts\n",
        "| Case | Columns | Lines | Width (ft) | Internal breaks | "
        "Inter-word breaks | Score | Measured width (ft) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for path in sorted(_INPUT.glob("*.porta")):
        source = path.read_text()
        title = source.splitlines()[0].removeprefix("# ")
        building = solve(parse(source))
        lo = min(room.x for room in building.rooms if room.x is not None)
        hi = max(room.x + room.width for room in building.rooms if room.x is not None)
        entries = _entries(building)
        portable = TextMetrics()
        measured = choose_layout(
            entries, hi - lo, metrics, metrics["1 square = 5 ft"].width
        )
        production = choose_layout(
            entries, hi - lo, portable, portable["1 square = 5 ft"].width
        )
        assert measured is not None
        assert production is not None
        html.append(f'<article><h2>{escape(title)}</h2><div class="pair">')
        for label, suffix, svg in (
            (
                "Measured reference",
                "measured",
                _review_svg(building, measured, metrics),
            ),
            ("Production", "production", render.render_svg(building)),
        ):
            target = _OUTPUT / f"{path.stem}-{suffix}.svg"
            outputs[target] = svg
            html.append(
                f'<figure><p>{label}</p><a href="{target.name}">'
                f'<img src="{target.name}" alt="{escape(title)}: {label}"></a></figure>'
            )
        html.append("</div></article>")
        report.append(
            f"| {title} | {len(production.columns)} | {production.lines} "
            f"| {production.width:.3f} | {production.splits} "
            f"| {interword_breaks(production)} | {production.score:.3f} "
            f"| {measured.width:.3f} |"
        )
    outputs[_OUTPUT / "index.html"] = "\n".join(html)
    outputs[_OUTPUT / "results.md"] = "\n".join(report) + "\n"
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Stale review output: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if args.export_png:
        for path in outputs:
            if path.name.endswith("-production.svg"):
                root = ET.fromstring(outputs[path])
                width = float(root.attrib["viewBox"].split()[2])
                subprocess.run(
                    [
                        args.export_png,
                        str(path),
                        f"--export-filename={path.with_suffix('.png')}",
                        f"--export-width={min(3000, max(600, round(width * 10)))}",
                    ],
                    check=True,
                )
    print("\n".join(report))


if __name__ == "__main__":
    main()
