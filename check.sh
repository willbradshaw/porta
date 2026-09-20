#!/bin/sh
# Run all checks, or one named check for CI and targeted local validation.
set -eu
cd -- "$(dirname -- "$0")"

if [ "$#" -eq 0 ]; then
    set -- test lint format types docs build
fi

# Validate every argument before running any checks.
for check in "$@"; do
    case "$check" in
        test|lint|format|types|docs|build) ;;
        *) echo "Usage: $0 [test|lint|format|types|docs|build ...]" >&2; exit 2 ;;
    esac
done

run_check() {
    case "$1" in
        test) uv run --extra dev pytest ;;
        lint) uv run --extra dev ruff check . ;;
        format) uv run --extra dev ruff format --check . ;;
        types) uv run --extra dev mypy ;;
        docs) uv run python src/build_figures.py --check ;;
        build) uv build ;;
    esac
}

for check in "$@"; do
    echo "Running $check"
    if run_check "$check"; then
        echo "Passed $check"
    else
        status=$?
        echo "Failed $check (exit $status)" >&2
        exit "$status"
    fi
done
