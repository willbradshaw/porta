#!/bin/sh
# Run the complete project checks locally and in CI.
set -eu
cd -- "$(dirname -- "$0")"

run() {
    echo "Running: $*"
    if "$@"; then
        return 0
    else
        status=$?
        echo "Failed: $* (exit $status)" >&2
        exit "$status"
    fi
}

run uv run --extra dev pytest
run uv run --extra dev ruff check .
run uv run --extra dev ruff format --check .
run uv run --extra dev mypy
run uv run python src/build_figures.py --check
run uv build
