"""Tests for ``cli.py``: argument parsing and the end-to-end pipeline."""

from pathlib import Path

import pytest

import porta
from porta.cli import build_parser, main
from porta.layout import solve
from porta.parser import parse
from porta.render import render_ascii, render_svg

MANOR = "examples/manor.porta"

OVERLAPPING = (
    'room a "A" 40x20 root\n'
    'room b "B" 20x20 down-of a\n'
    'room c "C" 20x20 right-of b\n'
    'room d "D" 20x40 up-of c'
)


def manor_svg() -> str:
    return render_svg(solve(parse(Path(MANOR).read_text())))


def manor_ascii() -> str:
    return render_ascii(solve(parse(Path(MANOR).read_text())))


# --- argument parsing ------------------------------------------------------


def test_version_is_present() -> None:
    assert porta.__version__


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert porta.__version__ in capsys.readouterr().out


def test_draw_subcommand_parses() -> None:
    args = build_parser().parse_args(["draw", "manor.porta", "-o", "manor.svg"])
    assert args.command == "draw"
    assert args.input == "manor.porta"
    assert args.output == "manor.svg"
    assert args.debug_ascii is False


def test_debug_ascii_flag_parses() -> None:
    args = build_parser().parse_args(["draw", "manor.porta", "--debug-ascii"])
    assert args.debug_ascii is True


def test_help_uses_a_command_metavar() -> None:
    help_text = build_parser().format_help()
    assert "{draw}" not in help_text
    assert "<command>" in help_text


# --- end-to-end: SVG -------------------------------------------------------


def test_draw_writes_svg_to_a_file(tmp_path: Path) -> None:
    out = tmp_path / "manor.svg"
    assert main(["draw", MANOR, "-o", str(out)]) == 0
    assert out.read_text() == manor_svg()


def test_draw_writes_svg_to_stdout_without_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["draw", MANOR]) == 0
    assert capsys.readouterr().out.startswith("<svg")


# --- end-to-end: ASCII -----------------------------------------------------


def test_debug_ascii_prints_grid_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["draw", MANOR, "--debug-ascii"]) == 0
    assert capsys.readouterr().out.rstrip("\n") == manor_ascii()


def test_debug_ascii_writes_to_a_file(tmp_path: Path) -> None:
    out = tmp_path / "manor.txt"
    assert main(["draw", MANOR, "--debug-ascii", "-o", str(out)]) == 0
    assert out.read_text() == manor_ascii()


# --- diagnostics -----------------------------------------------------------


def test_parse_error_reports_file_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.porta"
    bad.write_text('room a "A" 20x20 root\nroom b "B" 20x21 right-of a')
    assert main(["draw", str(bad)]) == 1
    assert f"{bad}:2: error:" in capsys.readouterr().err


def test_overlap_error_names_both_rooms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "overlap.porta"
    bad.write_text(OVERLAPPING)
    assert main(["draw", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "'a'" in err
    assert "'d'" in err


def test_missing_input_file_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.porta"
    assert main(["draw", str(missing)]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "nope.porta" in err
