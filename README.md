# porta

A small CLI that turns a concise, **relational** textual spec of a building's
layout into a clean, printable **SVG** floor plan — for tabletop-RPG session
prep.

You describe rooms by their dimensions and how they sit relative to one
another; `porta` solves the geometry and renders it. No mouse, no coordinates
to hand-pack, diffable in git.

```
# manor.floor — feet, 5-ft grid, north = up
room entrance "Entrance Hall"  20x20   root
room kitchen  "Kitchen"        20x30   west-of entrance
room hall     "Great Hall"     40x30   north-of entrance  east-of kitchen
```

```sh
uv run porta draw manor.floor -o manor.svg
uv run porta draw manor.floor --debug-ascii   # eyeball the solved layout
```

## Status

Early scaffold. The DSL, layout engine, and renderer are stubs — see
[`docs/design.md`](docs/design.md) for the full spec and build phasing.

## Develop

```sh
uv run porta --help
uv run --with pytest pytest
```

## Use as a dependency

```sh
uv add --editable ../porta   # from a consuming project, during development
```
