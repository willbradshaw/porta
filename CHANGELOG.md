# Changelog

Notable changes per release, newest first.

## Unreleased

## 1.1.0 (2026-06-07)

- Non-rectangular rooms via `block <id> "<name>" [glyph=<member>] <member>...`:
  group rooms into one space, dropping the walls and doors they share with each
  other; the union renders with a single outline, glyph, and key entry.
  Validates membership and contiguity, and warns on suppressed names/doors.
- Optional room names: an empty name slot (`""`) leaves a room unlabelled (the
  key then lists it by glyph alone).
- The map key lists rooms and blocks by glyph and name only — per-room
  dimensions are no longer shown (rectangular and non-rectangular rooms read
  the same way).
- Non-fatal warnings: solving collects advisories that the CLI prints to stderr
  (the run still succeeds with exit 0).
- Add a Blocks guide (`docs/block.md`), linked from the README and the room and
  door guides.
- Tooling: a changelog, a workflow that auto-drafts a GitHub release on a
  version bump, and a CI check requiring a changelog entry on every PR.

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
