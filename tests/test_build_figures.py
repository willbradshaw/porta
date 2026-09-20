"""Check documentation figures without overwriting reviewed output."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("state", ["current", "stale", "missing", "invalid"])
def test_check_figures_is_read_only(tmp_path: Path, state: str) -> None:
    script = tmp_path / "src" / "build_figures.py"
    script.parent.mkdir()
    shutil.copyfile("src/build_figures.py", script)
    docs = tmp_path / "docs"
    docs.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text('```porta docs/room.svg\nroom hall "Hall" 10x10 root\n```\n')
    command = [sys.executable, str(script)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    figure = docs / "room.svg"
    if state == "stale":
        figure.write_text("reviewed but outdated figure")
    elif state == "missing":
        figure.unlink()
    elif state == "invalid":
        readme.write_text("```porta\nnot a valid statement\n```\n")
    before = figure.read_bytes() if figure.exists() else None

    result = subprocess.run(
        [*command, "--check"], check=False, capture_output=True, text=True
    )

    assert result.returncode == (0 if state == "current" else 1)
    assert (figure.read_bytes() if figure.exists() else None) == before
    if state in {"stale", "missing"}:
        assert "docs/room.svg" in result.stderr
        assert "uv run python src/build_figures.py" in result.stderr
    elif state == "invalid":
        assert "README.md: in example" in result.stderr
