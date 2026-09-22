# Changelog

Notable changes per release, newest first.

## Unreleased

- Replace the scale caption with a labeled 20-ft scale bar and a grid-size note.
- Refine SVG typography, grid, and spacing, and automatically balance room-key
  columns and wrapping. Keep key-layout scoring parameters in a separate JSON file.

## 1.7.0 (2026-09-20)

- Add standalone `window` statements between rooms or to the outside, rendered
  as double lines with white interiors, with shared sizing and placement code.
  Document placement and block boundaries, including a manor capstone mixing
  doors and windows; reserve `window` as a keyword.
  Integrate windows with derived interior/exterior walls, outdoor rooms, and
  automatic door widths, with interaction examples and regression goldens.
- Add a room `exterior` attribute using normal relational placement, dimensions,
  and labels. Adjacent exterior rooms get automatic dashed dividers, and exposed
  edges inside the plan grid get dashed demarcation. Blocks
  suppress boundaries between members. Blocks cannot mix interior and exterior
  rooms. Explicit doors on wall-free outdoor edges are rejected (existing block
  suppression still applies).
- Draw exposed building walls at 1.6 times the interior stroke width, deriving walls
  across the whole plan and drawing shared spans once while preserving block
  boundaries, openings, doors, dividers, and stairs.
- Add automatic door width (`door=?`) to span the full shared wall or exterior
  side, including open and secret doors and component-link doors.
  Cover all declaration forms with SVG goldens and show an automatic opening
  in the door reference capstone.
- Report an actionable, format-neutral error when automatic room/block glyphs
  run out in SVG or ASCII rendering, and document the capacity and workarounds.
- Correct the room, block, and door references for reserved IDs, forward
  references, automatic glyphs, block connectivity, and door dimensions and
  offsets, with examples of forward references and a partially exposed wall.
- Add a root `check.sh` shared by local development and CI, check documentation
  figures without modifying them, and add `uv` setup to the README.
  Remove downstream-repository assumptions from agent instructions.
- Move shared coding-agent instructions to `AGENTS.md`, retaining `CLAUDE.md`
  as a compatibility entry point, and link all six DSL reference pages.

## 1.6.0 (2026-08-05)

- Dividers: `divider <a> <b>` draws the suppressed boundary between two
  members of a block as a thin dashed dividing line, cut wherever a stair
  entrance lies on it (see `docs/divider.md`).
- `divider` is now a reserved word and cannot be used as a room id.

## 1.5.0 (2026-08-04)

- Stairs: `stairs <up|down|in> <room> down=<side>` draws a flight of
  narrowing treads inside a room — up/down off the floor or between levels
  within it — with optional `size=` and `at=` placement; room glyphs move
  aside, and inaccessible flights or doors blocked by one are errors (see
  `docs/stairs.md`).
- `stairs` and `in` are now reserved words and cannot be used as room ids.

## 1.4.0 (2026-08-01)

- Disconnected components: a plan may contain several groups of rooms, each
  with its own `root`; components are solved independently and packed into a
  top-aligned row with a 10 ft gap (see `docs/room.md`).
- Component links: `link <room> <relation> <room>` joins two disconnected
  components flush, exactly like a relation between the two rooms, with the
  usual align/shift and door modifiers (see `docs/link.md`).
- `link` is now a reserved word and cannot be used as a room id.

## 1.3.0 (2026-07-26)

- Open boundaries: marking a door `open` (e.g. `door=20 open`) removes the
  wall across its span and draws a dotted line instead of a door mark; both
  rooms keep their own glyphs and key entries (see `docs/door.md`).
- Secret doors: marking a door `secret` (e.g. `door=5@5 secret`) draws the
  usual door mark with the conventional "S" over it and records the door as
  secret in the model (see `docs/door.md`).
- Line continuation: end a line with a whitespace-separated backslash to
  continue a statement onto the next line (see the README).
- `open` and `secret` are now reserved words and cannot be used as room ids.

## 1.2.0 (2026-07-26)

- Explicit display glyphs on rooms and blocks: `glyph="12"` (1-3 printable
  characters) labels the entity verbatim in the plan and key, so a
  transcribed layout can keep its source's area numbers (see `docs/room.md`).
- Unlabeled rooms and blocks: `glyph=""` suppresses the glyph and the key
  entry entirely.
- Automatic glyph assignment never collides with explicit glyphs; duplicate
  explicit glyphs raise an error, and an explicit glyph on a block member is
  suppressed with a warning (like member names).
- Rendering: SVG glyphs shrink to fit narrow rooms; the `--debug-ascii` grid
  pads cells to the widest glyph and renders unlabeled rooms' cells as `_`;
  map keys sort shortest-glyph-first so `1`..`9` precede `10`.

## 1.1.0 (2026-06-07)

- Implement non-rectangular spaces via `block` statements, representing
  unions of rectangular rooms (see `docs/block.md`).
- Makes room (and block) names optional by permitting empty (`""`) name entries.
- Remove per-room dimensions from map keys.
- Add non-fatal warnings for explicit doors or non-empty names on walls
  suppressed by `block` statements.
- Added `CHANGELOG.md`, plus CI to ensure it's updated on every PR.
- Added a workflow to auto-draft GitHub releases whenever the package 
  version is updated in `pyproject.toml`.

## 1.0.1 (2026-06-07)

- Drop the README's embedded figure (PyPI doesn't render SVG); the Rooms and
  Doors guides still carry figures.
- Add a PyPI Trusted Publishing workflow (releases publish via GitHub Actions).
- Fix a typo in the doors guide.

## 1.0.0 (2026-06-07)

- Initial release.
- Relational `.porta` DSL: rooms placed by `up-of` / `down-of` / `left-of` /
  `right-of`, with `align`, `shift`, and `?` auto-dimensions.
- Doors: drawn on shared walls by default, plus `no-door`, `door=W@O`,
  standalone `door a b`, and external `door <room> outside <side>`.
- `porta draw` renders SVG (or `--debug-ascii`); `porta --version`.
- Zero runtime dependencies, fully typed, MIT licensed.
