"""Check key scoring, wrapping, and entry partitioning."""

import json
from pathlib import Path

import pytest

from porta import render
from porta.key_layout import (
    candidates,
    partition_entries,
    text_fragments,
    wrap_name,
)
from porta.layout import solve
from porta.model import Building
from porta.parser import parse
from porta.text_metrics import TextBounds


def _entries(building: Building) -> list[tuple[str, str]]:
    """Get legend entries through the renderer's glyph and ordering rules."""
    glyphs = render._assign_glyphs(building)
    by_id = {room.id: room for room in building.rooms}
    return [
        (glyphs[eid], render._key_name(building, by_id, eid))
        for eid in render._legend_ids(building, render._member_block(building), glyphs)
    ]


def sample_metrics(entries: list[tuple[str, str]]) -> dict[str, TextBounds]:
    """Synthetic measurements keep the scoring arithmetic independent of fonts."""
    return {
        text: TextBounds(0, -4, len(text) * 3.5, 5)
        for entry in entries
        for value in entry
        for text in text_fragments(value) | {value}
    }


def test_four_lines_at_map_width_has_zero_badness() -> None:
    # Each column: 3.5-ft glyph + 2-ft gap + 3.5-ft name; two columns + gutter = 24.
    entries = [(str(i), "A") for i in range(8)]
    options = candidates(entries, 24, sample_metrics(entries))
    best = min(options, key=lambda c: (c.score, len(c.columns)))
    assert len(best.columns) == 2
    assert best.lines == 4
    assert best.width == 24
    assert best.score == 0


@pytest.mark.parametrize("count", [1, 4, 8, 16, 42])
def test_candidates_preserve_entries_and_do_not_wrap(count: int) -> None:
    entries = [(str(i), f"UnbrokenName{i}") for i in range(count)]
    options = candidates(entries, 100, sample_metrics(entries), wrap=False)
    assert len(options) == count
    assert len(options[0].columns) == 1
    for candidate in options:
        assert all(candidate.columns)
        assert [entry for column in candidate.columns for entry in column] == entries
        assert candidate.lines == max(len(column) for column in candidate.columns)
        assert len(set(candidate.widths)) == 1
        assert candidate.width <= sum(candidate.widths) + 6 * (
            len(candidate.columns) - 1
        )
        assert candidate.score == pytest.approx(
            ((candidate.lines - 4) / 4) ** 2
            + ((candidate.width - 100) / 100) ** 2
            * (0.5 if candidate.width < 100 else 1)
        )


@pytest.mark.parametrize(("map_width", "expected"), [(80, 2), (20, 1)])
def test_wide_and_tall_cases_choose_different_column_counts(
    map_width: int, expected: int
) -> None:
    names = [
        "Guardroom",
        "Armory",
        "Gallery",
        "Chapel",
        "Library",
        "Kitchen",
        "Pantry",
        "Vault",
    ]
    entries = [(str(i), name) for i, name in enumerate(names, 1)]
    options = candidates(entries, map_width, sample_metrics(entries), wrap=False)
    best = min(options, key=lambda c: (c.score, len(c.columns)))
    assert len(best.columns) == expected


def test_empty_key_has_no_candidates() -> None:
    assert candidates([], 20, {}) == []


@pytest.mark.parametrize(
    ("name", "width", "expected"),
    [
        ("Red blue green", 28, ["Red blue", "green"]),
        ("abcdef", 7, ["ab", "cd", "ef"]),
    ],
)
def test_wrapping_uses_measured_word_and_character_bounds(
    name: str, width: float, expected: list[str]
) -> None:
    assert wrap_name(name, width, sample_metrics([("1", name)])) == expected


def test_wrapped_candidates_use_equal_widths_and_count_rendered_lines() -> None:
    entries = [("1", "Red blue green"), ("100", "abcdef"), ("3", "Red")]
    options = candidates(entries, 30, sample_metrics(entries))
    assert any(len(c.rows["Red blue green"]) > 1 for c in options)
    for c in options:
        assert len(set(c.widths)) == len(set(c.glyph_widths)) == 1
        assert [entry for col in c.columns for entry in col] == entries
        assert c.lines == max(sum(len(c.rows[n]) for _, n in col) for col in c.columns)
        for name, rows in c.rows.items():
            assert "".join(rows).replace(" ", "") == name.replace(" ", "")


def test_partition_balances_lines_without_splitting_entries() -> None:
    entries = [(str(i), name) for i, name in enumerate(["a", "b", "c", "d"])]
    rows = {"a": ["a"] * 4, "b": ["b"], "c": ["c"], "d": ["d"]}
    assert partition_entries(entries, rows, 2) == [entries[:1], entries[1:]]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("Store", ["S", "t", "o", "r", "e"], 4),
        ("Red blue", ["Red", "blue"], 0),
        ("Red blue", ["Re", "d", "bl", "ue"], 2),
        ("Red blue", ["Red blue"], 0),
    ],
)
def test_internal_word_break_count(name: str, rows: list[str], expected: int) -> None:
    from porta.key_layout import word_splits

    assert word_splits(name, rows) == expected


def test_scale_width_sets_target_and_split_penalty_counts_duplicate_entries() -> None:
    from porta.key_layout import penalized

    entries = [("1", "Store"), ("2", "Store")]
    options = candidates(entries, 5, sample_metrics(entries), scale_width=30)
    for c in options:
        assert c.width_cost == pytest.approx(
            ((c.width - 30) / 30) ** 2 * (0.5 if c.width < 30 else 1)
        )
        assert penalized(c, 4).score == pytest.approx(c.score + 4 * c.splits)
    narrow = max(options, key=lambda c: c.splits)
    assert narrow.splits == 8


@pytest.mark.parametrize("coefficient", [1, 0.75, 0.5])
def test_height_coefficient_only_scales_height_cost(coefficient: float) -> None:
    from dataclasses import replace

    from porta.key_layout import penalized

    entries = [("1", "Store")]
    for c in candidates(entries, 30, sample_metrics(entries)):
        weighted = replace(penalized(c, 0.5), height_coefficient=coefficient)
        assert weighted.score == pytest.approx(
            coefficient * ((c.lines - 4) / 4) ** 2
            + ((c.width - 30) / 30) ** 2 * (0.5 if c.width < 30 else 1)
            + 0.5 * c.splits
        )
        assert weighted.rows == c.rows


@pytest.mark.parametrize("penalty", [0, 0.1, 0.15, 0.2])
def test_interword_penalty_excludes_internal_breaks_and_counts_each_entry(
    penalty: float,
) -> None:
    from porta.key_layout import interword_breaks, with_interword_penalty

    entries = [("1", "Red blue"), ("2", "Red blue")]
    options = candidates(entries, 30, sample_metrics(entries))
    assert any(c.splits for c in options)
    assert any(interword_breaks(c) for c in options)
    for c in options:
        total_breaks = 2 * (len(c.rows["Red blue"]) - 1)
        ordinary = total_breaks - c.splits
        assert interword_breaks(c) == ordinary
        assert with_interword_penalty(c, penalty).score == pytest.approx(
            0.7 * c.height_cost
            + c.width_cost
            + 0.5 * c.splits
            + penalty * ordinary
            + c.imbalance_ratio
        )


@pytest.mark.parametrize("name", ["", "   ", "Store"])
def test_empty_names_and_single_entries_remain_valid(name: str) -> None:
    from porta.key_layout import choose_layout
    from porta.text_metrics import TextMetrics

    metrics = TextMetrics()
    choice = choose_layout([("1", name)], 5, metrics, metrics["1 square = 5 ft"].width)
    assert choice is not None
    assert choice.lines >= 1
    assert choice.width > 0


@pytest.mark.parametrize(
    "case",
    sorted(Path("tests/fixtures/key-layouts").glob("*.porta")),
    ids=lambda path: path.stem,
)
def test_production_metrics_preserve_reviewed_layout_choices(case: Path) -> None:
    from porta.key_layout import choose_layout
    from porta.text_metrics import TextMetrics

    building = solve(parse(case.read_text()))
    entries = _entries(building)
    left = min(r.x for r in building.rooms if r.x is not None)
    right = max(r.x + r.width for r in building.rooms if r.x is not None)
    expected = json.loads(Path("tests/fixtures/key-layouts/expected.json").read_text())[
        "cases"
    ][case.stem]
    portable = TextMetrics()
    actual = choose_layout(
        entries, right - left, portable, portable["1 square = 5 ft"].width
    )
    assert actual is not None
    assert [[g for g, _ in col] for col in actual.columns] == expected["columns"]
    assert actual.rows == expected["rows"]
    assert actual.width == pytest.approx(expected["measured_width"], abs=0.05)


@pytest.mark.parametrize(
    ("heights", "expected"),
    [
        ([3], 1),
        ([4, 4], 1),
        ([1, 2, 1], 2),
        ([3, 3, 2], 1.5),
    ],
)
def test_imbalance_counts_wrapped_lines_and_glyph_only_entries(
    heights: list[int],
    expected: float,
) -> None:
    from dataclasses import replace

    from porta.key_layout import with_interword_penalty

    entries = [(str(i), str(i)) for i in range(len(heights))]
    base = candidates(entries, 30, sample_metrics(entries), wrap=False)[-1]
    rows = {
        name: [name] * height if height > 1 else []
        for (_, name), height in zip(entries, heights, strict=True)
    }
    candidate = replace(base, rows=rows)
    assert candidate.column_lines == heights
    assert candidate.imbalance_ratio == expected
    assert with_interword_penalty(candidate).imbalance_cost == expected


@pytest.mark.parametrize(("target", "expected"), [(18, 0.125), (9, 0), (6, 0.25)])
def test_asymmetric_width_cost(target: float, expected: float) -> None:
    # Synthetic glyph + gap + name occupy exactly nine feet.
    entries = [("1", "A")]
    candidate = candidates(entries, target, sample_metrics(entries), wrap=False)[0]
    assert candidate.width == 9
    assert candidate.width_cost == pytest.approx(expected)


def test_block_capstone_prefers_one_unwrapped_column() -> None:
    from porta.key_layout import choose_layout
    from porta.text_metrics import TextMetrics

    building = solve(
        parse(Path("tests/fixtures/key-layouts/07-block-capstone.porta").read_text())
    )
    metrics = TextMetrics()
    chosen = choose_layout(
        _entries(building), 80, metrics, metrics["1 square = 5 ft"].width
    )
    assert chosen is not None
    assert chosen.column_lines == [3]
    assert chosen.rows["Great Hall"] == ["Great Hall"]


def test_short_key_does_not_wrap_just_to_approach_four_lines() -> None:
    from porta.key_layout import choose_layout
    from porta.text_metrics import TextMetrics

    metrics = TextMetrics()
    chosen = choose_layout(
        [("H", "Great Hall")], 40, metrics, metrics["1 square = 5 ft"].width
    )
    assert chosen is not None
    assert chosen.column_lines == [1]
    assert chosen.rows["Great Hall"] == ["Great Hall"]
