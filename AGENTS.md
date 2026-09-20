# porta

A standalone Python package: a relational DSL for authoring D&D floor plans and
rendering them to SVG. CLI-driven, zero runtime dependencies.

The user-facing references are [`docs/room.md`](docs/room.md) (rooms, placement,
auto-dimensions, validation), [`docs/door.md`](docs/door.md) (doors),
[`docs/block.md`](docs/block.md) (blocks), [`docs/divider.md`](docs/divider.md)
(dividers), [`docs/link.md`](docs/link.md) (links), and
[`docs/stairs.md`](docs/stairs.md) (stairs). For exact behaviour the code is the
source of truth. The body below is just working conventions.

## Orientation

- **What it does** — parse a `.porta` spec (rooms + relational placement) →
  resolve geometry by DAG propagation → render SVG.
- **Package layout** — `src/porta/`: `cli.py` (argparse entry), `parser.py`
  (`.porta` → model), `model.py` (dataclasses), `layout.py` (relations →
  coordinates, validation), `render.py` (model → SVG/ASCII), `errors.py` (the
  `PortaError` hierarchy, each carrying a source line). Tests in `tests/`.
  `src/build_figures.py` regenerates the doc figures (a dev tool, not shipped).

## Workflow

- Run with **`uv`**: `uv run porta draw <in>.porta -o <out>.svg`.
- Run `./check.sh` before pushing; CI uses the same script. See
  [Development](README.md#development) for setup, targeted checks, generated
  artifacts, and the required changelog update.
- Doc figures (`docs/img/`) are generated from fenced ` ```porta ` examples
  (those with a path on the fence) in `README.md` and `docs/*.md` by
  `src/build_figures.py` — don't hand-edit them, and keep the examples valid
  (every one is solved on each build).
- Run project Python commands through **`uv run python`**.
- Use **relative paths** in shell/git commands, from the repository root.
- Quote shell paths and provide usable file links when referencing files.

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
