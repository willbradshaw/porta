"""Tests for ``layout.py``: DAG propagation, structural validation, overlap.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up = smaller y). Each room's stored ``(x, y)`` is its top-left (NW)
corner; the root's NW corner is the origin.
"""

from pathlib import Path

import pytest

from porta.errors import LayoutError, OverlapError
from porta.layout import find_overlaps, solve
from porta.model import Building, Room
from porta.parser import parse


def coords(text: str, room_id: str) -> tuple[int | None, int | None]:
    room = solve(parse(text)).room(room_id)
    return room.x, room.y


def placed(room_id: str, x: int, y: int, w: int, h: int) -> Room:
    return Room(id=room_id, name=room_id, width=w, height=h, x=x, y=y)


def building_of(*rooms: Room) -> Building:
    return Building(list(rooms))


# --- placement -------------------------------------------------------------


def test_root_is_placed_at_the_origin() -> None:
    assert coords('room a "A" 20x20 root', "a") == (0, 0)


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        # Anchor 'a' is 20x20 at the origin; 'b' is 10x10. Free axis align-starts.
        ("right-of", (20, 0)),  # west edge meets a's east edge; tops flush
        ("left-of", (-10, 0)),  # east edge meets a's west edge; tops flush
        ("down-of", (0, 20)),  # north edge meets a's south edge; lefts flush
        ("up-of", (0, -10)),  # south edge meets a's north edge; lefts flush
    ],
)
def test_single_relation_edge_math_and_align_start(
    relation: str, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a'
    assert coords(text, "b") == expected


# The design-note manor: two relations pin both axes of 'hall' directly.
DESIGN_MANOR = (
    'room entrance "Entrance Hall" 20x20 root\n'
    'room kitchen  "Kitchen"       20x30 left-of entrance\n'
    'room hall     "Great Hall"    40x30 up-of entrance right-of kitchen'
)


@pytest.mark.parametrize(
    ("room_id", "expected"),
    [
        ("entrance", (0, 0)),
        ("kitchen", (-20, 0)),  # left-of entrance; tops flush
        ("hall", (0, -30)),  # y from up-of entrance, x from right-of kitchen
    ],
)
def test_two_relations_pin_both_axes(room_id: str, expected: tuple[int, int]) -> None:
    assert coords(DESIGN_MANOR, room_id) == expected


def test_align_start_propagates_to_create_a_gap() -> None:
    # 'smoking' is east of the tall hall and north of 'drawing'; because
    # 'drawing' align-started to hall's top, 'smoking' rises above the hall's
    # roofline, leaving the south-east corner empty (the spec's §2.4 surprise).
    text = (
        'room hall    "Hall"    20x40 root\n'
        'room drawing "Drawing" 20x20 right-of hall\n'
        'room smoking "Smoking" 20x20 right-of hall up-of drawing'
    )
    assert coords(text, "drawing") == (20, 0)
    assert coords(text, "smoking") == (20, -20)


# --- shift -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("relation", "shift", "expected"),
    [
        # Anchor 'a' is 20x20 at the origin; 'b' is 10x10. Positive shift is
        # east (for up/down-of) or south (for left/right-of).
        ("up-of", 10, (10, -10)),
        ("up-of", -10, (-10, -10)),
        ("down-of", 10, (10, 20)),
        ("down-of", -10, (-10, 20)),
        ("left-of", 10, (-10, 10)),
        ("left-of", -10, (-10, -10)),
        ("right-of", 10, (20, 10)),
        ("right-of", -10, (20, -10)),
    ],
)
def test_shift_nudges_along_the_free_axis(
    relation: str, shift: int, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a shift={shift}'
    assert coords(text, "b") == expected


def test_shift_propagates_to_dependents() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 up-of a shift=10\n'
        'room c "C" 10x10 up-of b'
    )
    assert coords(text, "b") == (10, -10)
    assert coords(text, "c") == (10, -20)  # c stacks on the shifted b


def test_shift_with_both_axes_constrained_raises() -> None:
    # 'up-of' shifts along x, but 'right-of' already pins x -> no free axis.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a shift=10 right-of a'
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- structural validation -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('room a "A" 10x10', id="no-root"),
        pytest.param('room a "A" 10x10 root\nroom b "B" 10x10 root', id="two-roots"),
        pytest.param(
            'room a "A" 10x10 root up-of b\nroom b "B" 10x10 down-of a',
            id="root-with-relations",
        ),
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x10 right-of ghost',
            id="unknown-anchor",
        ),
        pytest.param(
            'room r "R" 10x10 root\nroom a "A" 10x10 up-of b\nroom b "B" 10x10 up-of a',
            id="cycle",
        ),
        pytest.param('room r "R" 10x10 root\nroom a "A" 10x10', id="disconnected"),
        pytest.param(
            'room a "A" 10x10 root\n'
            'room c "C" 10x10 right-of a\n'
            'room b "B" 10x10 left-of a right-of c',
            id="same-axis-over-constraint",
        ),
    ],
)
def test_layout_validation_raises(text: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_unknown_anchor_error_points_at_the_relation_line() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 right-of ghost'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert exc.value.line == 2


# --- overlap detection -----------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected_rect"),
    [
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 10, 10, 20, 20),
            (10, 10, 10, 10),
            id="partial-corner-overlap",
        ),
        pytest.param(
            placed("a", 0, 0, 40, 40),
            placed("b", 10, 10, 10, 10),
            (10, 10, 10, 10),
            id="b-fully-contained-in-a",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 40),
            placed("b", 10, 0, 20, 40),
            (10, 0, 10, 40),
            id="half-overlap",
        ),
    ],
)
def test_find_overlaps_reports_intersection_rectangle(
    a: Room, b: Room, expected_rect: tuple[int, int, int, int]
) -> None:
    overlaps = find_overlaps(building_of(a, b))
    assert len(overlaps) == 1
    first, second, rect = overlaps[0]
    assert (first.id, second.id) == ("a", "b")
    assert rect == expected_rect


@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 20, 0, 20, 20),
            id="flush-shared-vertical-edge",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 0, 20, 20, 20),
            id="flush-shared-horizontal-edge",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 20, 20, 20, 20),
            id="corner-touching-only",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 100, 100, 20, 20),
            id="fully-disjoint",
        ),
    ],
)
def test_flush_and_touching_rooms_do_not_overlap(a: Room, b: Room) -> None:
    assert find_overlaps(building_of(a, b)) == []


def test_find_overlaps_finds_every_colliding_pair() -> None:
    # Three mutually overlapping rooms -> all three pairs.
    overlaps = find_overlaps(
        building_of(
            placed("a", 0, 0, 30, 30),
            placed("b", 10, 10, 30, 30),
            placed("c", 20, 20, 30, 30),
        )
    )
    pairs = {(first.id, second.id) for first, second, _ in overlaps}
    assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}


def test_solved_manor_has_no_overlaps() -> None:
    source = Path("examples/manor.porta").read_text()
    assert find_overlaps(solve(parse(source))) == []


# 'd' loops back over the root 'a' via the b->c->d chain.
OVERLAPPING = (
    'room a "A" 40x20 root\n'
    'room b "B" 20x20 down-of a\n'
    'room c "C" 20x20 right-of b\n'
    'room d "D" 20x40 up-of c'
)


def test_solve_raises_overlap_error_with_rooms_and_rectangle() -> None:
    # Read the collision off the real solve path: 'a' (root) and 'd' overlap
    # on (20, 0, 20, 20). The error carries this structurally for the CLI.
    with pytest.raises(OverlapError) as exc:
        solve(parse(OVERLAPPING))
    assert exc.value.rooms == ("a", "d")
    assert exc.value.rect == (20, 0, 20, 20)
