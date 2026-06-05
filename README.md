# porta

A small CLI that turns a concise, **relational** textual spec of a building's
layout into a clean, printable **SVG** floor plan — for tabletop-RPG session
prep.

You describe rooms by their dimensions and how they sit relative to one
another; `porta` solves the geometry and renders it. No mouse, no coordinates
to hand-pack, diffable in git.

```
# feet, 5-ft grid
room entrance "Entrance Hall"  20x20   root
room kitchen  "Kitchen"        20x30   left-of entrance
room hall     "Great Hall"     40x30   up-of entrance  right-of kitchen
```

```sh
uv run porta draw manor.porta -o manor.svg
uv run porta draw manor.porta --debug-ascii   # eyeball the solved layout
```

Rooms attach **flush** by one relation per axis (`up-of` / `down-of` /
`left-of` / `right-of`); positions are derived, not authored. See
[`examples/manor.porta`](examples/manor.porta) for a fuller example.

## Status

Working: parse → solve placement (validation: one root, no cycles, no
disconnected rooms, no overlaps) → render SVG (5-ft grid, glyph labels + key)
and an ASCII debug view. Relations take `align=start|end` and `shift`, and
**doors are on by default** (`no-door` to suppress, `door=W@O` to size/place,
standalone `door a b` between any adjacent pair). Not yet implemented (tracked
as issues): derived interior/exterior walls, non-rectangular rooms,
external/outside doors, windows, multi-floor, and richer styling. See
[`docs/design.md`](docs/design.md) for the full spec and phasing.

## Develop

```sh
uv run porta --help
uv run --extra dev pytest
```

## Use as a dependency

```sh
uv add --editable ../porta   # from a consuming project, during development
```
