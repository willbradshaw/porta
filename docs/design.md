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

- `up-of` / `down-of` pin the **vertical** relationship: the new room's facing
  edge meets the anchor's facing edge, flush. The **horizontal** position is
  left free.
- `left-of` / `right-of` pin the **horizontal** relationship; the **vertical**
  position is left free.

The two families are **orthogonal**. So
`hall up-of entrance right-of kitchen` pins **both** axes directly — `y` from
the up relation, `x` from the right relation — with no ambiguity.

Relations are **page-relative**, not compass (`up`/`down`/`left`/`right`); the
words `above`/`below` are reserved for future multi-floor stacking.
Coordinates are integer feet, **x increasing east (right), y increasing south
(down)** — SVG-native, so the renderer draws in feet with no axis flip. The
root sits at the origin `(0, 0)`; each room's `(x, y)` is its top-left corner.

### 2.2 The free axis uses an alignment default

When a room has a relation on only one axis, the perpendicular axis falls to a
default. **Default = `align=start`**: the new room's top edge (for left/right
relations) or left edge (for up/down relations) aligns flush with the anchor's
same edge. Chosen for predictability — tiled rows form continuous walls.

Overrides on the free axis:

- `align=end` — far-edge alignment (shipped). `align=center` is deferred (#22):
  it lands off the 5-ft grid.
- `shift=N` — signed nudge of N feet along the free axis after aligning
  (shipped); must keep a shared wall (no detaching).
- `align-with <room>` — share an edge line with a *third* room (deferred, #6).

### 2.3 Same-axis pairs are a consistency check (snug-fit)

Two relations on the **same** axis (`right-of kitchen left-of pantry`)
over-determine that axis. `porta` should then **validate that the room's
dimension exactly fills the gap** and error if it doesn't. Useful, but
**nice-to-have** and not yet implemented (deferred, #4).

### 2.4 Worked example

```
# feet, 5-ft grid
room entrance "Entrance Hall"  40x20   root
room kitchen  "Kitchen"        20x40   down-of entrance
room hall     "Great Hall"     20x20   right-of kitchen  down-of entrance
```

- `entrance` — root, placed at origin.
- `kitchen` — `down-of entrance` pins its top edge to entrance's bottom edge;
  horizontal free → `align=start` (left edges flush).
- `hall` — `right-of kitchen` pins `x`, `down-of entrance` pins `y`. Fully
  determined, and it shares a real wall with each anchor.

Every relation must form a real shared wall (§3). A relation that ends up
meeting its anchor only at a corner is rejected, not silently accepted as a
coordinate-only pin: e.g. `smoking right-of hall up-of drawing`, where
`up-of drawing` lifts smoking clear above the tall hall's top, so `right-of
hall` touches only at a corner. Picturing two-axis placements is still the
tricky part, which is why `--debug-ascii` exists.

---

## 3. Validation & errors

Error-reporting quality is the main engineering effort, not layout. All errors
carry the offending room id(s) and source line number.

- **Exactly one root** (a room with `root`; `at X,Y` is a deferred alternative,
  #7). Zero or many → error.
- **No dependency cycles** (`A up-of B`, `B up-of A`).
- **No disconnected rooms** (every non-root room must resolve from the root).
- **No overlap** — after solving, no two room rectangles may collide.
  **Essential.** Error reports both ids and the overlap rectangle.
- **Shared walls** — every relation must share at least 5 ft of wall with its
  anchor. A relation that meets its anchor only at a corner (often because the
  other axis pushed the room past it), or a shift that detaches it, is rejected.
- **Doors** — every door must lie on a real shared wall and fit within it; two
  doors on the same wall may not overlap each other.
- **Over-constraint conflict** — same-axis relations that disagree (see
  snug-fit, deferred).

`--debug-ascii` prints the *solved* grid so placement can be eyeballed without
opening the SVG.

---

## 4. Syntax

One line per room:

```
room <id> "<Name>" <W>x<H> [root] [<relation> <anchor> [modifiers] ...]
```

- Dimensions in **feet**, on a **5-ft grid** (multiples of 5).
- Relations: `up-of <id>`, `down-of <id>`, `left-of <id>`, `right-of <id>`.
- Per-relation modifiers: `align=start|end`, `shift=N`, and the door controls
  below. (`at X,Y`, `type=<type>`, and `align=center` are deferred.)
- Comments: `#` to end of line. File extension: **`.porta`**.

### Doors

Doors are **on by default**: every relation whose two rooms share a real wall
gets a centred 5-ft door. Control them per relation:

- `no-door` — suppress the default door on that relation.
- `door[=W][@O]` — override it: width `W` ft, offset `O` ft from the wall's near
  end (top for vertical walls, left for horizontal). Both multiples of 5;
  default width 5, default offset centred (rounded down to the grid).

A **standalone** door connects *any* two adjacent rooms, not just an anchor
pair — e.g. two rooms placed against a common neighbour that end up side by
side:

```
door[=W][@O] <a> <b>
```

Two doors between the same pair are allowed (a pair of openings); two doors that
overlap each other are an error. Doors render as short thick lines and are
omitted from the ASCII view.

Later directives, not yet built: external/outside doors (#24), `window <room>
<side> ...`, `token "<name>" <room> ...`, `partition ...`, `floor "<name>"`
blocks.

---

## 5. Output

- **SVG only.** Source of truth, diffable. (Rasterizing to PNG for Obsidian
  embedding is the *consumer's* job, handled in the isles repo, not here.)
- **Rooms** as rectangles, each with a glyph label, plus a **key** mapping
  glyphs to names and noting the scale.
- **Doors** as short thick marks on the shared walls.
- **A 5-ft grid** behind the plan; geometry is drawn in feet, framed by the
  viewBox.
- **Deferred:** distinguishing derived interior vs exterior (envelope) walls
  (#17), `type=` style themes (#9), richer in-room name labels (#13), and nicer
  key / scale-bar / compass furniture (#16).

---

## 6. Phasing

- **Shipped** — rectangular rooms; `up/down/left/right-of` relations with
  `align=start|end` and `shift`; doors (default-on, `no-door`, `door=W@O`,
  standalone `door a b`); 5-ft grid; glyph labels + key; SVG out;
  `--debug-ascii`; validation (one root, cycles, disconnected, **overlap**,
  door fit/adjacency/overlap).
- **Next** — derived/stronger walls (interior vs exterior envelope, #17);
  non-rectangular rooms (#11); snug-fit validation for same-axis pairs (#4).
- **Later** — external doors (#24), windows, tokens, partitions/curtains,
  multi-floor on one image, lot view (garden/fence/gates/paths/trees),
  furniture symbols, `type=` style themes, richer labels.

---

## 7. Packaging & relationship to isles

- Standalone Python package, **zero runtime dependencies** (SVG via stdlib
  string/XML templating; the issue's `svgwrite` idea is optional and avoided
  for now). Dev deps: `pytest`, `ruff`, `mypy`. Toolchain: `uv`.
- CLI entry point: `porta draw <input>.porta -o <output>.svg [--debug-ascii]`.
- **isles consumes porta** as an editable local path dependency during
  development (`uv add --editable ../porta`), pinned to a tag/version once
  stable. The `.porta` sources and rendered SVGs live **in the isles vault**
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
