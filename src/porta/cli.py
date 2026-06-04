"""Command-line entry point for porta.

Thin orchestration: read a ``.porta`` file, parse it, solve the layout, render
the result, and write/print it. Owns top-level error presentation and the
process exit code.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the ``porta`` CLI.

    Returns:
        The configured top-level argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="porta",
        description="Render relational floor-plan specs (.porta) to SVG.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draw = sub.add_parser("draw", help="Render a .porta file to SVG.")
    draw.add_argument("input", help="Path to the input .porta file.")
    draw.add_argument("-o", "--output", help="Path to write the SVG output.")
    draw.add_argument(
        "--debug-ascii",
        action="store_true",
        help="Print the solved layout as an ASCII grid.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the porta CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "draw":
        raise SystemExit("porta draw: not implemented yet (Stage 0 skeleton)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
