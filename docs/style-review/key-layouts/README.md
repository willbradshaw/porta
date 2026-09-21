# Key-layout review cases

Six fixed `.porta` inputs in `tests/fixtures/key-layouts/` exercise the approved
production key algorithm. The [gallery](index.html) compares recorded full-string
Palatino measurements with the portable metrics used by the renderer.
[Results](results.md) report the selected layouts and scores.

| Case | Entries | Map size | Purpose |
| --- | ---: | --- | --- |
| Tiny store | 1 | 5 × 5 ft | Scale wider than map |
| Small cottage | 4 | 30 × 30 ft | Short key |
| Wide barracks | 8 | 80 × 30 ft | Horizontal space |
| Tall barracks | 8 | 20 × 120 ft | Same names, narrower map |
| Medium house | 16 | 100 × 80 ft | Varied names, Unicode, mixed glyphs, long token |
| Large keep | 42 | 140 × 90 ft | Column count, wrapping, and width/height tradeoffs |

The approved formula is
`B = 0.7((L - 4)/4)² + ((W - T)/T)² + 0.5S + 0.1R`.
See [the visual specification](../../svg-style.md) for definitions, candidate
search, and metric limitations. No further coefficient is under test here.
Production and measured-reference cases share the same scoring implementation.

Run from the repository root:

```sh
uv run python src/build_key_review.py
uv run python src/build_key_review.py --check
uv run python src/build_key_review.py --export-png /path/to/inkscape
```

The last command exports the six standalone production PNGs. It needs Inkscape
and Palatino installed; normal generation and rendering require neither.
To refresh recorded whole-string measurements or portable character metrics:

```sh
uv run python src/build_key_review.py --measure /path/to/inkscape
uv run python src/build_text_metrics.py /path/to/inkscape
```

Only run measurement refreshes on a machine with Palatino Regular installed,
and inspect resulting differences. Font substitution would invalidate the
Palatino reference. No fonts or outlines are copied into the package.

The corpus remains fixed while the score changes. Tests verify the approved
formula, entry order, wrapped line counts, equal column widths, break categories,
and agreement between production choices and independently measured references.
