# Default SVG appearance

Porta uses black architectural lines, a quiet measuring grid, and normal-weight
serif text. Rendering requires no style statement, downloaded font, or runtime
dependency.

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
B = 0.7 b ((L - 4) / 4)² + a ((W - T) / T)² + 0.5 S + 0.15 R + L / l
a = 0.5 when W < T, otherwise 1
b = 0.85 when L < 4, otherwise 1
```

- `L`: rendered line count in the tallest column, including wrapped lines.
- `l`: rendered line count in the shortest column; glyph-only entries count as one.
- `W`: visible key width, including gutters.
- `T`: maximum of map width and scale-caption width, excluding margins.
- `S`: line breaks inside words, summed across key entries.
- `R`: between-word line breaks within entries, excluding internal-word breaks.

Both shorter and taller keys are penalized relative to four lines, with a 0.85
multiplier below four (effective coefficient 0.595 rather than 0.7). Both narrower
and wider keys are penalized relative to the target width, with half the cost
for being narrower. The longest/shortest ratio has coefficient 1. Single-column
and equal-height layouts both add 1; an empty key has no layout to score. Wrapping prefers words,
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

All seven reviewed cases select the same columns and wrapping with portable metrics
as with full-string Inkscape measurements; their key widths differ by less than
0.05 map feet. SVGs retain ordinary editable text and the approved fallback stack.
The measured bounds apply to Palatino; substituted fonts can change visible fit.
Room-label fitting retains its conservative Unicode-aware width estimates.

## Reproduction and remaining review

Regenerate documentation figures with `uv run python src/build_figures.py`.
The seven key-layout regression cases are `key-*.porta` / `key-*.svg` pairs
in `tests/fixtures/layouts/`. They run through the same complete-SVG golden
comparison as the other layout fixtures, without system fonts or review tooling.

Refresh the portable font metrics with
`uv run python src/build_text_metrics.py /path/to/inkscape` only on a machine
with Palatino Regular installed, and inspect the resulting differences.
Normal rendering and tests require neither Inkscape nor an installed font.
Review both complete compositions and enlarged text; a print proof and
fallback-font review remain useful.

A follow-up to #99/#16 will review the scale bar proposal, text color, background,
and any further spacing refinements. This PR retains the original caption and colors.
The [column-height imbalance follow-up](https://github.com/willbradshaw/porta/issues/102)
is implemented by the ratio term. The partition search remains unchanged.
