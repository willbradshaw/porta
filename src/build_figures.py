"""Build (and check) the figures embedded in the docs.

Every fenced ``porta`` block in ``docs/*.md`` is parsed and solved, so a broken
or stale example fails the build. When the fence carries a path —

    ```porta img/snug-fit.svg
    room a "A" 10x10 root
    ...
    ```

— the block is also rendered to that path (relative to the markdown file). The
path lives in the fence, which GitHub doesn't render, so the reader sees only
the code and the separate ``![](img/snug-fit.svg)`` image.

    uv run python src/build_figures.py
"""

import re
from pathlib import Path

from porta.layout import solve
from porta.parser import parse
from porta.render import render_svg

_BLOCK = re.compile(
    r"^```porta(?:[ \t]+(?P<path>\S+))?[ \t]*\n(?P<body>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)

# Light grey reads more gently than white on a dark page (tweak to taste).
_BACKGROUND = "#e0e0e0"


def main() -> None:
    docs = Path(__file__).parent.parent / "docs"
    for md in sorted(docs.glob("*.md")):
        for block in _BLOCK.finditer(md.read_text()):
            building = solve(parse(block["body"]))  # raises on a bad example
            path = block["path"]
            if path is None:
                continue
            target = md.parent / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_svg(building, background=_BACKGROUND))
            print(f"{md.name}: wrote {path}")


if __name__ == "__main__":
    main()
