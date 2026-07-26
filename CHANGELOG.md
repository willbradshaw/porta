# Changelog

Notable changes per release, newest first.

## Unreleased

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
