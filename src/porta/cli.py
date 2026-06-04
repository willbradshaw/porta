"""Command-line entry point for porta.

Thin orchestration: read a ``.porta`` file, parse it, solve the layout, render
the result, and write/print it. Owns top-level error presentation and the
process exit code: expected bad input (a :class:`~porta.errors.PortaError` or
an unreadable file) becomes a tidy diagnostic and a non-zero exit, while
genuine bugs propagate as tracebacks.
"""

import argparse
import sys
from pathlib import Path

from porta.errors import PortaError
from porta.layout import solve
from porta.parser import parse
from porta.render import render_ascii, render_svg


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
    draw.add_argument("-o", "--output", help="Output file (default: stdout).")
    draw.add_argument(
        "--debug-ascii",
        action="store_true",
        help="Render the solved layout as an ASCII grid instead of SVG.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the porta CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Process exit code (0 on success, 1 on bad input).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "draw":
        return _draw(args.input, args.output, args.debug_ascii)
    return 0


def _draw(input_path: str, output_path: str | None, debug_ascii: bool) -> int:
    """Render ``input_path`` and write the result; return the exit code.

    ``--debug-ascii`` selects the format (ASCII vs SVG); ``output_path`` selects
    the destination (a file, or stdout when ``None``).
    """
    try:
        source = Path(input_path).read_text()
    except OSError as exc:
        message = exc.strerror or str(exc)
        print(f"error: cannot read {input_path}: {message}", file=sys.stderr)
        return 1

    try:
        building = solve(parse(source))
    except PortaError as exc:
        print(_format_diagnostic(input_path, exc), file=sys.stderr)
        return 1

    output = render_ascii(building) if debug_ascii else render_svg(building)
    if output_path is None:
        print(output)
    else:
        Path(output_path).write_text(output)
    return 0


def _format_diagnostic(source_name: str, error: PortaError) -> str:
    """Format a PortaError as a compiler-style ``file:line: error: message``."""
    where = f"{source_name}:{error.line}" if error.line is not None else source_name
    return f"{where}: error: {error.message}"


if __name__ == "__main__":
    sys.exit(main())
