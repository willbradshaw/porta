# porta — design note

`porta` is a small CLI that turns a concise, **relational** textual spec of a
building's layout into a clean, printable **SVG** floor plan, for tabletop-RPG
session prep. You describe rooms by their dimensions and how they sit relative
to one another ("the great hall is north of the entrance but east of the
kitchen"); `porta` solves the geometry and renders it.

This document is the canonical spec. It supersedes the draft note from
`willbradshaw/isles` issue #145 (itself a continuation of the closed PR #124).
The original wishlist is preserved in the appendix; the body below records the
decisions that actually govern the build.

---

## 1. Why a relational DSL (and not the alternatives)

The problem space, as surveyed in #145:

- **Procedural generators** (Watabou, Inkarnate AI) draw a layout *for* you —
  useless when you have specific architectural intent.
- **GUI editors** (Dungeondraft, Dungeon Scrawl) draw exactly what you want but
  need a mouse, can't be diffed in git, and don't live alongside campaign text.
- **Graph diagram tools** (D2, Mermaid, Graphviz) render *connectivity*, not
  *spatial layout* — wrong shape for tactical play.
- **Hand-written SVG / TikZ** is exact but verbose and error-prone.

The candidate input models we weighed:

1. **Data formats (YAML / JSON / TOML) with explicit `(x, y, w, h)`.** Rejected.
   They encode coordinates as data, so the source never resembles the map; you
   hand-pack and hand-sync every coordinate. (YAML rejected outright; TOML is
   *worse* for lists of homogeneous records — every room becomes a `[[room]]`
   block.)
2. **Grid-art (ASCII regions → rooms).** Genuinely spatial and great for agents
   "seeing" their own output, but fixed-resolution, and doors/windows live
   awkwardly between cells. Set aside.
3. **Relational placement with explicit dimensions.** **Chosen.** You give each
   room a size and how it attaches to its neighbours; positions are derived.

### The key insight that makes relational tractable

Because **every room carries its own `WxH`** and attaches **flush**, there is
**nothing numerical to solve** — no constraint solver. Placement is
**deterministic propagation through a dependency graph (a DAG)**: place a root
room, then each other room's position is fully computed from an
already-placed anchor's edges plus a relation. Topological order, one pass.
This is a scene-graph / CSS-flow shape, not Z3.

---

## 2. Placement model

### 2.1 Relations pin one axis each

- `north-of` / `south-of` pin the **vertical** relationship: the new room's
  facing edge meets the anchor's facing edge, flush. The **horizontal**
  position is left free.
- `east-of` / `west-of` pin the **horizontal** relationship; the **vertical**
  position is left free.

The two families are **orthogonal**. So
`hall north-of entrance east-of kitchen` pins **both** axes directly — `y`
from the north relation, `x` from the east relation — with no ambiguity.

Convention: **north = up** (smaller screen-`y`). Internally the renderer flips
to SVG's y-down space.

### 2.2 The free axis uses an alignment default

When a room has a relation on only one axis, the perpendicular axis falls to a
default. **Default = `align-start`**: the new room's north edge (for E/W
relations) or west edge (for N/S relations) aligns flush with the anchor's same
edge. Chosen for predictability — tiled rows form continuous walls.

Overrides:

- `align=center` / `align=end` — center or far-edge alignment on the free axis.
- `align-with <room>` — share an edge line with a *third* room (deferred).
- `gap=N` — insert N feet instead of a flush shared wall (corridor / yard).
- `shift=N` — nudge N feet along the free axis after aligning.

### 2.3 Same-axis pairs are a consistency check (snug-fit)

Two relations on the **same** axis (`east-of kitchen west-of pantry`)
over-determine that axis. `porta` then **validates that the room's dimension
exactly fills the gap** and errors if it doesn't. Useful, but **nice-to-have**,
not v1-blocking.

### 2.4 Worked example

```
# feet, 5-ft grid, north = up
room entrance "Entrance Hall"  20x20   root
room kitchen  "Kitchen"        20x30   west-of entrance
room hall     "Great Hall"     40x30   north-of entrance  east-of kitchen
```

- `entrance` — root, placed at origin.
- `kitchen` — `west-of entrance` pins its east edge to entrance's west edge;
  vertical free → `align-start` (north edges flush).
- `hall` — `north-of entrance` pins `y`, `east-of kitchen` pins `x`. Fully
  determined.

Three-room subtlety (align-start propagates): with `drawing-room east-of hall`
then `smoking-room east-of hall north-of drawing-room`, the smoking-room stacks
*above* drawing-room — and because drawing-room align-started to hall's *top*,
smoking-room ends up above the hall's roofline, leaving a gap east of hall's
lower half. `south-of drawing-room` instead drops it into that gap for a tidy
block. This "picture it / trust the solver" cost is why `--debug-ascii` exists.

---

## 3. Validation & errors

Error-reporting quality is the main engineering effort, not layout. All errors
carry the offending room id(s) and source line number.

- **Exactly one root** (a room with `root`, or `at X,Y`). Zero or many → error.
- **No dependency cycles** (`A north-of B`, `B north-of A`).
- **No disconnected rooms** (every non-root room must resolve from the root).
- **No overlap** — after solving, no two room rectangles may collide.
  **Essential, v1.** Error reports both ids and the overlap rectangle.
- **Over-constraint conflict** — same-axis relations that disagree (see snug-fit).

`--debug-ascii` prints the *solved* grid so placement can be eyeballed without
opening the SVG.

---

## 4. Syntax (v1)

One line per room:

```
room <id> "<Name>" <W>x<H> [root | at X,Y] [<relation> ...] [type=<type>]
```

- Dimensions in **feet**, on a **5-ft grid** (multiples of 5).
- Relations: `north-of <id>`, `south-of <id>`, `east-of <id>`, `west-of <id>`,
  each optionally `align=…`, `gap=N`, `shift=N`.
- Comments: `#` to end of line.
- File extension: **`.floor`**.

Later directives (post-v1): `door <a> <b>`, `window <room> <side> ...`,
`token "<name>" <room> ...`, `partition ...`, `floor "<name>"` blocks.

---

## 5. Output (v1)

- **SVG only.** Source of truth, diffable. (Rasterizing to PNG for Obsidian
  embedding is the *consumer's* job, handled in the isles repo, not here.)
- **Rooms** as rectangles with name labels and optional `type` styling.
- **Walls** derived: shared boundary → interior wall; envelope edge → exterior.
- **Outline** derived from the union of room rectangles (no authored envelope).
- **Auto furniture:** 5-ft grid, scale bar, N compass, legend. Generated, not
  authored.

---

## 6. Phasing

- **v1** — rectangles only; relations + `align`/`gap`/`shift`; derived
  walls + outline; auto grid/scale/compass/legend; SVG out; `--debug-ascii`;
  solid validation (one-root, cycles, disconnected, **overlap**).
- **v2** — doors (auto-placed at the shared wall the graph already knows about,
  so `door hall entrance` needs no coordinates); then non-rectangular rooms;
  snug-fit validation.
- **v3** — windows, tokens, partitions/curtains, multi-floor on one image,
  lot view (garden/fence/gates/paths/trees), furniture symbols.

---

## 7. Packaging & relationship to isles

- Standalone Python package, **zero runtime dependencies** (SVG via stdlib
  string/XML templating; the issue's `svgwrite` idea is optional and avoided
  for now). Dev dep: `pytest`. Toolchain: `uv`.
- CLI entry point: `porta draw <input>.floor -o <output>.svg [--debug-ascii]`.
- **isles consumes porta** as an editable local path dependency during
  development (`uv add --editable ../porta`), pinned to a tag/version once
  stable. The `.floor` sources and rendered SVGs live **in the isles vault**
  (a `maps/` dir, next to Location pages); the tool knows nothing about isles.

---

## 8. Open questions (resolve during the build)

- Exact grammar edge cases (quoting, multi-word types, relation ordering).
- `type` vocabulary and the default style theme (issue suggests cream formal /
  service tan / wet blue-grey / dais amber). Theme switch for player-facing
  maps?
- Multi-floor representation: stacked vs side-by-side; how voids/galleries that
  open to the floor below are expressed.
- License / whether to open-source.
- Coordinate origin and rounding conventions in the renderer.

---

## Appendix — original feature wishlist (from isles #145 / PR #124)

Preserved for reference; not all of this is committed. Room primitives with
`type` (formal / service / wet / circulation / hall / dais / back-of-house /
void) and sub-labels; non-rectangular L/T/H footprints; auto-derived walls;
doors as wall gaps with optional offset; windows as double-line indicators on
exterior walls with `count` and `style` (e.g. stained); curtains/partitions as
styled non-wall lines; tokens as named circles for NPC positions; multi-floor
stacked on one SVG with alignment preserved; lot view (garden fill, dashed
fence, gates, paths, trees); optional furniture (staircases, tables, beds,
altar, statues); auto grid + scale bar + N compass + legend; a
`--preview` render-and-open step for visual verification before commit.

Prior art consulted: D2 / Mermaid (graph, not spatial), TikZ/LaTeX (capable but
heavyweight), Watabou One Page Dungeon (JSON rooms+doors, renderer not
separable), Illwinter's Floorplan Generator (ASCII import), Dungeon Scrawl
(GUI, no scripting path).
