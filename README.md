# `porta`

`porta` is two things:

1. A **DSL** for concisely defining a relational floorplan; and
2. A **software package** for deterministically converting a floorplan into
   a clean SVG map.

```porta docs/img/readme.svg
room hall    "Great Hall" 40x20 root
room parlour "Parlour"    20x20 left-of hall
room kitchen "Kitchen"    20x20 right-of hall
room study   "Study"      ?x20  down-of parlour
```

<!-- PyPI can't render SVG, so the README shows a PNG raster of docs/img/readme.svg
via an absolute URL. If the example above changes, regenerate the PNG from the SVG
with inkscape (export to PNG at width 1000). -->
<img alt="Four rooms rendered to an SVG floor plan" src="https://raw.githubusercontent.com/willbradshaw/porta/main/docs/img/readme.png" width="60%">

## The `porta` DSL

`porta` floorplans are defined in `.porta` files adhering to a strict specification.
Each room is defined in a single line relative to one or more anchor rooms,
forming a dependency graph all the way back to the initial root room. This model
creates a 1-to-1 correspondence between the floorplan and the final SVG map it
produces, allowing `porta` to rapidly and deterministically generate one from
the other.

Files are read line by line: a `#` starts a comment that runs to the end of the
line (a `#` inside a quoted name is literal), and blank lines are ignored.

For more on the `porta` DSL specification, see the following documentation:

- [**Rooms**](docs/room.md) — the `room` statement, room positioning,
  auto-dimensions (`?`), and the layout resolution procedure.
- [**Doors**](docs/door.md) — default doors & how to modify them, and
  the `door` statement for explicitly adding non-default doors.

## The `porta` tool

Once a valid floorplan has been written, `porta draw` converts it into an
SVG map in a two-step process. First, the dependency graph is traversed
and the relations in the floorplan are converted into a coordinate system.
Second, that coordinate system is used to deterministically generate an
SVG file.

```sh
porta draw plan.porta -o plan.svg
```

The solved coordinate system can also be viewed and debugged directly
as an ASCII grid:

```sh
porta draw plan.porta --debug-ascii
```

A plan that can't be solved (due to overlaps, missing anchors, gaps
between a room and its anchor, etc) will fail and raise an error.

## Installation

`porta` is published on PyPI and can be installed with `pip`:

```sh
pip install porta
```

Alternatively, install it from a checkout of this repo. Add the `[dev]` extra
to pull in the test and lint tools as well:

```sh
pip install -e .          # editable install
pip install -e ".[dev]"   # ... plus pytest, ruff, and mypy
```

## Why `porta`?

`porta` is built to be:

- **Text-based** — a plan is plain text: editable in any editor, diffable, and
  version-controlled alongside your campaign notes. No WYSIWYG, no binary files.
- **Concise** — a terse syntax with strong defaults; a whole plan is a handful
  of short lines.
- **Deterministic** — no procedural generation and no randomness; the same plan
  always renders the same map.
- **Relational** — rooms are placed against other rooms, never drawn by hand or
  given raw coordinates.
- **Spatial** — the output is a flush, to-scale floor plan in tabletop
  conventions, not a flowchart or connectivity graph.
- **Fast** — placement is a single pass over a dependency graph, with no
  constraint solver to run.
- **AI-friendly** — terse, text-only, and predictable, so a language model can
  read and write plans reliably (this one falls out of the rest).

No existing tool hits all of these:

- **Procedural and AI generators** (Watabou, Inkarnate) aren't deterministic or
  controllable — they invent a layout instead of rendering yours.
- **GUI map editors** (Dungeondraft, Dungeon Scrawl) aren't text: mouse-driven,
  binary, and kept apart from your notes.
- **Diagram tools** (Mermaid, Graphviz, D2) give connectivity, not a spatial,
  to-scale map.
- **Hand-written SVG** is text, but neither concise nor relational — verbose and
  easy to get wrong.

