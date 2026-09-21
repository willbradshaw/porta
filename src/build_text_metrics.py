#!/usr/bin/env -S uv run python
"""Record portable Palatino metrics with Inkscape; no font outlines are copied.

Run `uv run python src/build_text_metrics.py /path/to/inkscape` on a machine with
Palatino Regular installed. The renderer consumes only the generated JSON.
"""

import argparse
import json
import string
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET


def main() -> None:
    """Measure character ink, advances, and pair adjustments in em units."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inkscape")
    args = parser.parse_args()
    chars = "".join(chr(i) for i in range(33, 383) if chr(i).isprintable())
    chars += "\u2018\u2019“”\u2013—…"
    pairchars = string.ascii_letters + "\u2019'.,:;!?-()0123456789"
    strings = sorted(
        set(chars)
        | {c + "|" for c in chars}
        | {"||", "| |"}
        | {a + b for a in pairchars for b in pairchars}
    )
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": "2000",
            "height": str(len(strings) * 20 + 20),
            "font-family": "Palatino",
            "font-size": "5",
            "font-weight": "400",
        },
    )
    for i, text in enumerate(strings):
        ET.SubElement(root, "text", id=f"m{i}", x="100", y=str(i * 20 + 10)).text = text
    with tempfile.TemporaryDirectory(prefix="porta-font-metrics-") as directory:
        path = Path(directory) / "metrics.svg"
        path.write_text(ET.tostring(root, encoding="unicode"))
        output = subprocess.check_output(
            [args.inkscape, str(path), "--query-all"], text=True
        )
    bounds: dict[str, tuple[float, float, float, float]] = {}
    for line in output.splitlines():
        key, *values = line.split(",")
        if key.startswith("m") and key[1:].isdigit():
            i = int(key[1:])
            x, y, width, height = map(float, values)
            bounds[strings[i]] = (x - 100, y - (i * 20 + 10), width, height)
    if len(bounds) != len(strings):
        raise ValueError("Incomplete Inkscape measurements")
    # The vertical bar has no kerning with these characters. Its right edge
    # reveals the preceding character's advance, including otherwise invisible space.
    right_bar = bounds["|"][0] + bounds["|"][2]
    space = bounds["| |"][2] - bounds["||"][2]
    glyphs = {" ": [round(space / 5, 6), 0, 0, 0, 0]}
    for char in chars:
        x, y, width, height = bounds[char]
        pair = bounds[char + "|"]
        advance = pair[0] + pair[2] - right_bar
        glyphs[char] = [round(v / 5, 6) for v in (advance, x, y, width, height)]
    pairs = {}
    for a in pairchars:
        for b in pairchars:
            x, _, width, _ = bounds[a + b]
            ga, gb = glyphs[a], glyphs[b]
            delta = (x + width) / 5 - ga[0] - gb[1] - gb[3]
            if abs(delta) > 0.001:
                pairs[a + b] = round(delta, 5)
    Path("src/porta/palatino_metrics.json").write_text(
        json.dumps(
            {
                "font": "Palatino Regular",
                "source": "Inkscape measured glyph advances, ink bounds, "
                "and pair adjustments; "
                "em units. No font outlines.",
                "glyphs": glyphs,
                "pairs": pairs,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
