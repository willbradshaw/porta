#!/usr/bin/env -S uv run python
"""Build (and check) the figures embedded in the docs.

Every fenced ``porta`` block in ``README.md`` and ``docs/*.md`` is parsed and
solved, so a broken or stale example fails the build. When the fence carries a
path —

    ```porta img/snug-fit.svg
    room a "A" 10x10 root
    ...
    ```

— the block is also rendered to that path (relative to the markdown file). The
path lives in the fence, which GitHub doesn't render, so the reader sees only
the code and the separate ``![](img/snug-fit.svg)`` image.

    uv run python src/build_figures.py           # render the figures
    uv run python src/build_figures.py --check   # validate snippets and figures
"""

import argparse
import re
from pathlib import Path

from porta.errors import PortaError
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
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate every snippet and check figures are current without writing",
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    md_files = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    stale: list[Path] = []
    for md in md_files:
        for block in _BLOCK.finditer(md.read_text()):
            try:
                building = solve(parse(block["body"]))
            except PortaError as err:
                first = block["body"].splitlines()[0]
                raise SystemExit(f"{md.name}: in example '{first}': {err}") from None
            path = block["path"]
            if path is None:
                continue
            target = md.parent / path
            rendered = render_svg(building, background=_BACKGROUND)
            if args.check:
                if not target.is_file() or target.read_text() != rendered:
                    stale.append(target.relative_to(root))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered)
            print(f"{md.name}: wrote {path}")
    if stale:
        paths = "\n".join(f"  {path}" for path in stale)
        raise SystemExit(
            f"Missing or stale figures:\n{paths}\n"
            "Regenerate with: uv run python src/build_figures.py"
        )


if __name__ == "__main__":
    main()
