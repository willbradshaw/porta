"""Stage 0 smoke tests: the package imports and the CLI parser is wired up."""

import porta
from porta.cli import build_parser


def test_version_is_present() -> None:
    assert porta.__version__


def test_draw_subcommand_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["draw", "manor.porta", "-o", "manor.svg"])
    assert args.command == "draw"
    assert args.input == "manor.porta"
    assert args.output == "manor.svg"
    assert args.debug_ascii is False


def test_debug_ascii_flag_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["draw", "manor.porta", "--debug-ascii"])
    assert args.debug_ascii is True
