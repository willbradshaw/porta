# Changelog

Notable changes per release, newest first.

## Unreleased

- Add this changelog.
- Add a workflow that drafts a GitHub release from the changelog on a version bump.
- Require a CHANGELOG update on every PR (CI check).
- Optional room names: an empty name slot (`""`) leaves a room unlabelled, and
  the key shows its dimensions instead of a name.
- Non-fatal warnings: solving collects advisories that the CLI prints to stderr
  (the run still succeeds with exit 0).

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
