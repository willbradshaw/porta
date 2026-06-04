"""Stage 3: overlap validation.

Detection is a pure primitive, ``find_overlaps``, returning the colliding room
pairs and their intersection rectangle ``(x, y, w, h)``. Flush-adjacent and
corner-touching rooms (zero-area intersection) do NOT count. ``solve`` runs the
check after placement and raises ``LayoutError`` naming both rooms.
"""

from pathlib import Path

import pytest

from porta.errors import OverlapError
from porta.layout import find_overlaps, solve
from porta.model import Building, Room
from porta.parser import parse


def placed(room_id: str, x: int, y: int, w: int, h: int) -> Room:
    return Room(id=room_id, name=room_id, width=w, height=h, x=x, y=y)


def building_of(*rooms: Room) -> Building:
    return Building(list(rooms))


# --- find_overlaps geometry ------------------------------------------------


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


# --- integration with solve ------------------------------------------------


def test_solved_manor_has_no_overlaps() -> None:
    source = Path("examples/manor.porta").read_text()
    assert find_overlaps(solve(parse(source))) == []


# 'd' loops back over the root 'a' via the b->c->d chain (see Stage 3 notes).
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
