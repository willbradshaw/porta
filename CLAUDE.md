# porta

A standalone Python package: a relational DSL for authoring D&D floor plans and
rendering them to SVG. CLI-driven, zero runtime dependencies.

**Read [`docs/design.md`](docs/design.md) first** — it is the canonical spec
(placement model, validation rules, syntax, phasing). The body below is just
working conventions.

## Orientation

- **What it does** — parse a `.porta` spec (rooms + relational placement) →
  resolve geometry by DAG propagation → render SVG.
- **Package layout** — `src/porta/`: `cli.py` (argparse entry), `parser.py`
  (`.porta` → model), `model.py` (dataclasses), `layout.py` (relations →
  coordinates, validation), `render.py` (model → SVG). Tests in `tests/`.
- **Consumer** — the `isles` D&D vault (sibling repo) installs porta via
  `uv add --editable ../porta`. The `.porta` sources and rendered SVGs live in
  *that* repo, not here. porta knows nothing about isles.

## Workflow

- Run with **`uv`**: `uv run porta draw <in>.porta -o <out>.svg`.
- Tests: `uv run --extra dev pytest`. CI runs them on push/PR.
- Use **`python`**, never `python3`.
- Use **relative paths** in shell/git commands.
- When handing the user a path to open, avoid spaces in it.

## Conventions

- Modern type hints (`list[str]`, `X | None`); dataclasses for the model.
- Google-style docstrings on public functions.
- Keep the runtime dependency-free: SVG via stdlib string/XML templating.
- Small, pure, testable functions — especially in `layout.py`, where geometry
  resolution and overlap detection should be unit-tested on tiny inputs.
- Tests: prefer `pytest.mark.parametrize` for families of similar cases (valid
  vs. invalid inputs, error conditions, geometry fixtures) over copy-pasted
  near-identical test functions. Once a test is parametrized, adding a case is
  one line — so be liberal and keep coverage comprehensive (give each case a
  readable `id`). Reserve standalone test functions for genuinely distinct
  assertions.
- Tests mirror the source: one `tests/test_<module>.py` per `src/porta/<module>.py`
  (e.g. `test_layout.py` covers all of `layout.py`). Error types in `errors.py`
  are tested where they're raised, not in a separate file.
