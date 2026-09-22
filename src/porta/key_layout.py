"""Score equal-width legend columns using portable or measured text bounds.

Tune the metric in the packaged key_layout.json; values load once on import.
All parameters must be finite and nonnegative, with target_lines positive.
"""

import json
from dataclasses import dataclass, fields, replace
from importlib.resources import files
from math import isfinite

from porta.style import DEFAULT_STYLE, Style
from porta.text_metrics import TextBounds


@dataclass(frozen=True)
class _Scoring:
    target_lines: float
    height_coefficient: float
    short_height_multiplier: float
    width_coefficient: float
    narrow_width_multiplier: float
    word_split_penalty: float
    interword_penalty: float
    imbalance_coefficient: float

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if (
                type(value) not in (int, float)
                or not isfinite(value)
                or value < 0
                or (field.name == "target_lines" and value == 0)
            ):
                raise ValueError(
                    f"Invalid key_layout.json parameter {field.name}: {value!r}"
                )


_SCORING = _Scoring(
    **json.loads(files("porta").joinpath("key_layout.json").read_text(encoding="utf-8"))
)


def text_fragments(name: str) -> set[str]:
    """Strings requiring measurements: word spans and emergency word fragments."""
    words = name.split()
    spans = {
        " ".join(words[i:j])
        for i in range(len(words))
        for j in range(i + 1, len(words) + 1)
    }
    spans.update(
        word[i:j]
        for word in words
        for i in range(len(word))
        for j in range(i + 1, len(word) + 1)
    )
    return spans | {name}


def wrap_name(name: str, width: float, metrics: dict[str, TextBounds]) -> list[str]:
    """Greedily wrap at spaces, splitting only words wider than the line."""
    words = name.split()
    rows = []
    start = 0
    while start < len(words):
        end = start
        for stop in range(start + 1, len(words) + 1):
            if metrics[" ".join(words[start:stop])].width <= width + 1e-9:
                end = stop
        if end > start:
            rows.append(" ".join(words[start:end]))
            start = end
            continue
        word = words[start]
        while word:
            length = max(
                (
                    i
                    for i in range(1, len(word) + 1)
                    if metrics[word[:i]].width <= width + 1e-9
                ),
                default=1,
            )
            rows.append(word[:length])
            word = word[length:]
        start += 1
    return rows


def partition_entries(
    entries: list[tuple[str, str]], rows: dict[str, list[str]], count: int
) -> list[list[tuple[str, str]]]:
    """Balance wrapped line counts in contiguous columns without splitting entries."""
    heights = [max(1, len(rows[name])) for _, name in entries]
    low, high = max(heights), sum(heights)
    while low < high:
        target = (low + high) // 2
        columns, used = 1, 0
        for height in heights:
            if used + height > target:
                columns += 1
                used = 0
            used += height
        if columns <= count:
            high = target
        else:
            low = target + 1
    result: list[list[tuple[str, str]]] = [[]]
    used = 0
    for i, (entry, height) in enumerate(zip(entries, heights, strict=True)):
        remaining = len(entries) - i
        if result[-1] and (used + height > low or remaining == count - len(result)):
            result.append([])
            used = 0
        result[-1].append(entry)
        used += height
    return result


@dataclass
class Candidate:
    """One candidate layout and its score components."""

    columns: list[list[tuple[str, str]]]
    widths: list[float]
    glyph_widths: list[float]
    rows: dict[str, list[str]]
    lines: int
    width: float
    left_trim: float
    height_cost: float
    width_cost: float
    splits: int = 0
    split_cost: float = 0
    height_coefficient: float = 1
    interword_cost: float = 0
    imbalance_cost: float = 0

    @property
    def column_lines(self) -> list[int]:
        """Return rendered line counts, including glyph-only entries."""
        return [
            sum(max(1, len(self.rows[name])) for _, name in column)
            for column in self.columns
        ]

    @property
    def imbalance_ratio(self) -> float:
        """Return longest/shortest; one column or equal heights give one."""
        lengths = self.column_lines
        return max(lengths) / min(lengths)

    @property
    def score(self) -> float:
        """Return height, asymmetric width, wrapping, and imbalance costs."""
        return (
            self.height_coefficient * self.height_cost
            + self.width_cost
            + self.split_cost
            + self.interword_cost
            + self.imbalance_cost
        )


def word_splits(name: str, rows: list[str]) -> int:
    """Count line boundaries inside words, ignoring whitespace boundaries."""
    word_ends = set()
    position = 0
    for word in name.split():
        position += len(word)
        word_ends.add(position)
    position = 0
    splits = 0
    for row in rows[:-1]:
        position += sum(len(word) for word in row.split())
        splits += position not in word_ends
    return splits


def penalized(candidate: Candidate, penalty: float) -> Candidate:
    """Apply a cost per internal word break without changing the layout."""
    return replace(candidate, split_cost=penalty * candidate.splits)


def interword_breaks(candidate: Candidate) -> int:
    """Count between-word line breaks across entries, excluding internal breaks."""
    return (
        sum(
            max(0, len(candidate.rows[name]) - 1)
            for column in candidate.columns
            for _, name in column
        )
        - candidate.splits
    )


def with_interword_penalty(
    candidate: Candidate, penalty: float | None = None
) -> Candidate:
    """Apply approved weights, optionally overriding the inter-word break cost."""
    return replace(
        penalized(candidate, _SCORING.word_split_penalty),
        height_coefficient=_SCORING.height_coefficient
        * (
            _SCORING.short_height_multiplier
            if candidate.lines < _SCORING.target_lines
            else 1
        ),
        interword_cost=(_SCORING.interword_penalty if penalty is None else penalty)
        * interword_breaks(candidate),
        imbalance_cost=_SCORING.imbalance_coefficient * candidate.imbalance_ratio,
    )


def candidates(
    entries: list[tuple[str, str]],
    map_width: float,
    metrics: dict[str, TextBounds],
    *,
    wrap: bool = True,
    scale_width: float = 0,
    style: Style = DEFAULT_STYLE,
) -> list[Candidate]:
    """Vary all nonempty column counts and text-wrap breakpoints.

    A common name-width limit varies at every measured word-span/fragment width;
    all columns share the same glyph and name widths. Column boundaries
    balance rendered line counts, preserve reading order, and keep entries whole.
    Internal word breaks are counted for later penalty comparisons. No column
    caps or minimum entry counts are imposed.
    """
    if not entries:
        return []
    target_width = max(map_width, scale_width)
    names = {name for _, name in entries}
    row_options = [{name: [name] if name.strip() else [] for name in names}]
    if wrap and any(name.strip() for name in names):
        fragments = {part for name in names for part in text_fragments(name)}
        minimum = max(
            metrics[char].width for name in names for char in name if not char.isspace()
        )
        widths = sorted(
            {
                metrics[part].width
                for part in fragments
                if metrics[part].width >= minimum
            },
            reverse=True,
        )
        seen = {tuple(tuple(row_options[0][name]) for name in sorted(names))}
        for width in widths:
            rows = {name: wrap_name(name, width, metrics) for name in names}
            signature = tuple(tuple(rows[name]) for name in sorted(names))
            if signature not in seen:
                seen.add(signature)
                row_options.append(rows)
    requested = style["key"]["columns"]
    counts = (
        range(1, len(entries) + 1)
        if requested == "auto"
        else [min(requested, len(entries))]
    )
    result = []
    for rows in row_options:
        for count in counts:
            columns = partition_entries(entries, rows, count)
            glyph_width = max(metrics[g].width for g, _ in entries)
            name_width = max(
                (metrics[line].width for name in names for line in rows[name]),
                default=0,
            )
            column_width = glyph_width + (
                style["key"]["identifier_gap_ft"] + name_width if name_width else 0
            )
            glyph_widths = [glyph_width] * count
            widths = [column_width] * count
            # Equal column pitches; center and score the visible ink, excluding
            # unused space at the two outside edges of the grid.
            left_trim = glyph_width - max(metrics[g].width for g, _ in columns[0])
            last_name_width = max(
                (metrics[line].width for _, name in columns[-1] for line in rows[name]),
                default=0,
            )
            right_trim = column_width - glyph_width
            if last_name_width:
                right_trim -= style["key"]["identifier_gap_ft"] + last_name_width
            lines = max(
                sum(max(1, len(rows[name])) for _, name in col) for col in columns
            )
            width = (
                sum(widths)
                + (count - 1) * style["key"]["column_gap_ft"]
                - left_trim
                - right_trim
            )
            result.append(
                Candidate(
                    columns,
                    widths,
                    glyph_widths,
                    rows,
                    lines,
                    width,
                    left_trim,
                    ((lines - _SCORING.target_lines) / _SCORING.target_lines) ** 2,
                    ((width - target_width) / target_width) ** 2
                    * _SCORING.width_coefficient
                    * (_SCORING.narrow_width_multiplier if width < target_width else 1),
                    sum(word_splits(name, rows[name]) for _, name in entries),
                )
            )
    return result


def choose_layout(
    entries: list[tuple[str, str]],
    map_width: float,
    metrics: dict[str, TextBounds],
    scale_width: float,
    *,
    style: Style = DEFAULT_STYLE,
) -> Candidate | None:
    """Choose the lowest approved score, breaking exact ties by column count."""
    return min(
        (
            with_interword_penalty(c)
            for c in candidates(
                entries,
                map_width,
                metrics,
                scale_width=scale_width,
                style=style,
            )
        ),
        key=lambda c: (c.score, len(c.columns)),
        default=None,
    )
