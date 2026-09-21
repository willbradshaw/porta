# Default SVG appearance

Porta uses black architectural lines, a quiet measuring grid, and normal-weight
serif text. Rendering requires no style statement, downloaded font, or runtime
dependency. The [before/after gallery](style-review/index.html) covers the manor,
tiny and narrow plans, blocks, outdoor areas, disconnected components, and symbols.
The [six-case key gallery](style-review/key-layouts/index.html) compares the
production layouts with independently measured Palatino text bounds.

## Approved visual rules

Dimensions are SVG user units (map feet).

| Element | Default |
| --- | --- |
| Typeface | Palatino, Georgia, Times New Roman, serif; normal weight (400) throughout |
| Room/block labels | 60% of the shorter available dimension; no fixed ceiling; shrink to fit 90% of width and avoid stairs |
| Grid | 5-ft squares, `#c4c4c4`, 0.125-ft stroke; clipped to room footprints |
| Walls | Existing black 0.8-ft exposed and 0.5-ft shared walls |
| Doors | Existing 1.5-ft solid/secret marks; secret S remains 5 ft with its halo |
| Other symbols | Existing open-door dots, windows, stairs, and divider weights |
| Margins | 10 ft |
| Key/scale text | 5 ft, with 8-ft key baseline spacing |
| Key alignment | Right-aligned visible glyphs, 2-ft gap, left-aligned names; 6-ft column gutters |
| Scale | Original “1 square = 5 ft” caption; 12 ft from map bottom to scale baseline, then 12 ft to first key baseline |

Grid lines remain globally aligned. Gaps between components and courtyard voids
are blank; declared outdoor rooms retain the grid and their dashed boundaries.
Room/block labels have no halo; secret-door markers retain their background halo.
Geometry, glyph assignment, key order, and validation semantics are unchanged.
The renderer's default page remains white; documentation retains its grey page.

## Key layout

The renderer searches column counts and one common wrapping width. Every column
has the same glyph reservation, name width, and gutter. Entries read down columns,
then left to right, and stay whole within a column. Contiguous partitions minimize
the tallest column's rendered line count. This is a deterministic partition rule,
not an exhaustive search of every partition.

The lowest score wins; exact ties prefer fewer columns:

```
B = 0.7 ((L - 4) / 4)² + ((W - T) / T)² + 0.5 S + 0.1 R
```

- `L`: rendered line count in the tallest column, including wrapped lines.
- `W`: visible key width, including gutters.
- `T`: maximum of map width and scale-caption width, excluding margins.
- `S`: line breaks inside words, summed across key entries.
- `R`: between-word line breaks within entries, excluding internal-word breaks.

Both shorter and taller keys are penalized relative to four lines; both narrower
and wider keys are penalized relative to the target width. Wrapping prefers words,
but overlong words may split. Candidate widths come from text wrap breakpoints;
there is no fixed 48-ft wrap width, three-column cap, or independent column-width
optimization. The canvas expands to fit the result without shrinking the text.
Visible text bounds determine centering, excluding unused outer grid-cell space.

## Portable text measurements

The package records Palatino Regular character advances, ink bounds, and common
pair adjustments in `src/porta/palatino_metrics.json`. These are numeric metrics,
not font outlines. Layout does not read system fonts or invoke a font tool.
Unsupported characters use conservative Unicode-aware estimates; combining
accents are normalized where possible. Arbitrary script shaping, ligatures, and
font substitution can differ from these estimates.

All six reviewed cases select the same columns and wrapping with portable metrics
as with full-string Inkscape measurements; their key widths differ by less than
0.05 map feet. SVGs retain ordinary editable text and the approved fallback stack.
The measured bounds apply to Palatino; substituted fonts can change visible fit.
Room-label fitting retains its conservative Unicode-aware width estimates.

## Reproduction and remaining review

```sh
uv run python src/build_style_review.py
uv run python src/build_key_review.py
uv run python src/build_key_review.py --check
uv run python src/build_figures.py
```

The before/after builder needs baseline commit
`9fc5e2644b30c478d95b5968806be813295359b1` in local Git history.
See the [key review instructions](style-review/key-layouts/README.md) for optional
PNG exports and refreshing font measurements. Review both complete compositions
and enlarged text; a print proof and fallback-font review remain useful.

A follow-up to #99/#16 will review the scale bar proposal, text color, background,
and any further spacing refinements. This PR retains the original caption and colors.
[Column-height imbalance](https://github.com/willbradshaw/porta/issues/102) is a
separate investigation; it is not an extra term in this formula.
