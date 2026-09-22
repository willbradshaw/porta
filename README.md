# `porta`

`porta` is two things:

1. A **DSL** for concisely defining a relational floorplan; and
2. A **software package** for deterministically converting a floorplan into
   a clean SVG map.

```porta
room hall    "Great Hall" 40x20 root
room parlour "Parlour"    20x20 left-of hall
room kitchen "Kitchen"    20x20 right-of hall
room study   "Study"      ?x20  down-of parlour
```

## The `porta` DSL

`porta` floorplans are defined in `.porta` files adhering to a strict specification.
Each room is defined in a single line relative to one or more anchor rooms,
forming a dependency graph all the way back to the initial root room. This model
creates a 1-to-1 correspondence between the floorplan and the final SVG map it
produces, allowing `porta` to rapidly and deterministically generate one from
the other.

Files are read line by line: a `#` starts a comment that runs to the end of the
line (a `#` inside a quoted name is literal), and blank lines are ignored.

Any statement can be **continued** onto the next physical line by ending it
with a backslash, separated from the last token by whitespace:

```porta
room pn "" 40x10 root
room pw "" 10x20 down-of pn
room pe "" 10x20 down-of pn align=end
room ps "" 40x10 down-of pw \
    down-of pe
block passages "Passages" glyph=pn \
    pn pw \
    pe ps
```

Continued lines parse as one statement, and errors still point at the
physical line of the offending token. A backslash anywhere else — mid-line,
glued to a token, or followed by a comment — is an error, as is a blank (or
comment-only) line inside a continued statement.

For more on the `porta` DSL specification, see the following documentation:

- [**Rooms**](docs/room.md) — the `room` statement, room positioning,
  auto-dimensions (`?`), disconnected components, and the layout
  resolution procedure.
- [**Windows**](docs/window.md) — interior and exterior windows, widths and offsets.
- [**Doors**](docs/door.md) — default doors & how to modify them, and
  the `door` statement for explicitly adding non-default doors.
- [**Blocks**](docs/block.md) — the `block` statement for joining
  multiple `room`s into a single non-rectangular space.
- [**Dividers**](docs/divider.md) — the `divider` statement for drawing
  a dividing line between two members of a block.
- [**Links**](docs/link.md) — the `link` statement for joining
  disconnected components into one continuous plan.
- [**Stairs**](docs/stairs.md) — the `stairs` statement for flights
  leading up or down off a floor, or between levels within one.

## The `porta` tool

`porta draw` resolves a floorplan's geometry and renders it as SVG or an ASCII
grid. Invalid plans produce an error.

```sh
porta draw plan.porta -o plan.svg
porta draw plan.porta --debug-ascii
porta draw plan.porta --style sepia.json -o plan.svg
```

Use `--style` with a JSON file to override rendering settings, for example:

```json
{"page": {"background": "#fff8e7", "line_color": "#332211"}}
```

[default_style.json](src/porta/default_style.json) documents all settings.
Overrides accept plain values or value/description records; omitted settings
keep their defaults. Unknown keys and invalid values produce an error.

Labels default to numbers; see [glyphs](docs/room.md#glyphs) for custom labels,
mnemonic assignment, and numbering starts. `--style` also works with
`--debug-ascii`, applying label settings while ignoring visual settings.

## Installation

`porta` requires Python 3.14 or newer and is published on PyPI:

```sh
pip install porta
```

Alternatively, install it from a checkout of this repo. Add the `[dev]` extra
to pull in the test and lint tools as well:

```sh
pip install -e .          # editable install
pip install -e ".[dev]"   # ... plus pytest, ruff, and mypy
```

For development with `uv`, set up the environment from the repository root:

```sh
uv sync --extra dev
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
