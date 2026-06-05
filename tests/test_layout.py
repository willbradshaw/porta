"""Tests for ``layout.py``: DAG propagation, structural validation, overlap.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up = smaller y). Each room's stored ``(x, y)`` is its top-left (NW)
corner; the root's NW corner is the origin.
"""

from pathlib import Path

import pytest

from porta.errors import LayoutError, OverlapError
from porta.layout import door_segments, find_overlaps, solve
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
        # east (for up/down-of) or south (for left/right-of). Magnitudes stay
        # small enough to keep b sharing a wall with a.
        ("up-of", 5, (5, -10)),
        ("up-of", -5, (-5, -10)),
        ("down-of", 5, (5, 20)),
        ("down-of", -5, (-5, 20)),
        ("left-of", 5, (-10, 5)),
        ("left-of", -5, (-10, -5)),
        ("right-of", 5, (20, 5)),
        ("right-of", -5, (20, -5)),
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
        'room b "B" 10x10 up-of a shift=5\n'
        'room c "C" 10x10 up-of b'
    )
    assert coords(text, "b") == (5, -10)
    assert coords(text, "c") == (5, -20)  # c stacks on the shifted b


def test_shift_with_both_axes_constrained_raises() -> None:
    # 'up-of' shifts along x, but 'right-of' already pins x -> no free axis.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a shift=10 right-of a'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_shift_that_detaches_from_the_anchor_raises() -> None:
    # shift = the room width slides b fully off a (corner-touch, no shared wall).
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 up-of a shift=10'
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- align -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        # Anchor 'a' is 20x20; 'b' is 10x10. align=end flushes the FAR edges,
        # so b sits at a's east (up/down-of) or south (left/right-of) end.
        ("up-of", (10, -10)),
        ("down-of", (10, 20)),
        ("left-of", (-10, 10)),
        ("right-of", (20, 10)),
    ],
)
def test_align_end_flushes_the_far_edge(
    relation: str, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a align=end'
    assert coords(text, "b") == expected


def test_align_end_composes_with_shift() -> None:
    # align=end puts b at the east edge (x=10), then shift nudges it west by 5.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a align=end shift=-5'
    assert coords(text, "b") == (5, -10)


def test_align_end_with_both_axes_constrained_raises() -> None:
    # align=end acts on x, but right-of already pins x -> no free axis.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a align=end right-of a'
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- doors -----------------------------------------------------------------


def doors_of(text: str) -> list[tuple[int, int, int, int]]:
    return door_segments(solve(parse(text)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # b (10x10) against a (20x20); shared wall is 10 ft long.
        # up-of: horizontal wall at y=0; 5-ft door centres (round down) to x[0,5].
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door', (0, 0, 5, 0)),
        # door=10 fills the wall.
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=10', (0, 0, 10, 0)),
        # explicit offset.
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=5@5', (5, 0, 10, 0)),
        # right-of: vertical wall at x=20; door spans y[0,5].
        ('room a "A" 20x20 root\nroom b "B" 10x10 right-of a door', (20, 0, 20, 5)),
    ],
)
def test_door_line_geometry(source: str, expected: tuple[int, int, int, int]) -> None:
    assert doors_of(source) == [expected]


@pytest.mark.parametrize(
    "source",
    [
        # door wider than the shared wall
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x10 up-of a door=20',
            id="door-wider-than-wall",
        ),
        # offset pushes the door past the wall
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=10@15',
            id="door-past-the-wall",
        ),
        # the door's relation only corner-touches its anchor (no shared wall)
        pytest.param(
            'room a "A" 10x10 root\n'
            'room b "B" 10x10 right-of a\n'
            'room c "C" 10x10 up-of a right-of b door',
            id="door-on-corner-touch",
        ),
    ],
)
def test_door_that_does_not_fit_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


def test_a_shared_wall_gets_a_default_door() -> None:
    # No 'door' modifier, but the shared wall gets a default 5-ft door.
    assert doors_of('room a "A" 20x20 root\nroom b "B" 20x20 right-of a') == [
        (20, 5, 20, 10)
    ]


def test_no_door_suppresses_the_default() -> None:
    assert doors_of('room a "A" 20x20 root\nroom b "B" 20x20 right-of a no-door') == []


def test_default_doors_skip_walls_that_only_corner_touch() -> None:
    # 'hall right-of kitchen' only corner-touches, so no default door there (and
    # no error); the two real walls (kitchen/entrance, hall/entrance) get one each.
    text = (
        'room entrance "E" 20x20 root\n'
        'room kitchen "K" 20x30 left-of entrance\n'
        'room hall "H" 40x30 up-of entrance right-of kitchen'
    )
    assert len(doors_of(text)) == 2


def test_standalone_door_between_incidental_rooms() -> None:
    # b and c are both below 'a' (not each other's anchor) but sit side by side,
    # sharing the x=20 wall; a standalone door connects them.
    text = (
        'room a "A" 40x20 root\n'
        'room b "B" 20x20 down-of a\n'
        'room c "C" 20x20 down-of a shift=20\n'
        "door b c"
    )
    assert (20, 25, 20, 30) in doors_of(text)


def test_standalone_door_between_nonadjacent_rooms_raises() -> None:
    # 'a' and 'c' only meet at a corner, so there is no wall to put a door on.
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 right-of a\n'
        'room c "C" 10x10 up-of b\n'
        "door a c"
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_standalone_door_to_unknown_room_raises() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 right-of a\ndoor a ghost'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_a_pair_can_have_two_doors() -> None:
    # The relation gives a default door; a standalone door adds a second on the
    # same wall -- deliberate, e.g. two openings between the rooms.
    text = 'room a "A" 20x40 root\nroom b "B" 20x40 right-of a\ndoor@30 a b'
    assert len(doors_of(text)) == 2


def test_overlapping_doors_raise() -> None:
    # Two doors on the same wall that overlap each other are a mistake.
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 20x20 right-of a no-door\n'
        "door=10@0 a b\n"
        "door@5 a b"
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- auto dimensions (?) ---------------------------------------------------


def dims(text: str, room_id: str) -> tuple[int, int]:
    room = solve(parse(text)).room(room_id)
    return room.width, room.height


def test_auto_height_matches_a_left_right_anchor() -> None:
    # right-of shares a vertical wall, so '?' height = the anchor's height.
    text = 'room a "A" 30x25 root\nroom b "B" 20x? right-of a'
    assert dims(text, "b") == (20, 25)


def test_auto_width_matches_an_up_down_anchor() -> None:
    # up-of shares a horizontal wall, so '?' width = the anchor's width.
    text = 'room a "A" 40x20 root\nroom b "B" ?x15 up-of a'
    assert dims(text, "b") == (40, 15)


def test_auto_both_dims_from_two_perpendicular_anchors() -> None:
    # right-of x sizes height (=20), down-of y sizes width (=10); position pinned.
    text = (
        'room x "X" 20x20 root\n'
        'room y "Y" 10x10 right-of x\n'
        'room r "R" ?x? right-of x down-of y'
    )
    assert dims(text, "r") == (10, 20)
    assert coords(text, "r") == (20, 10)


def test_auto_dim_chains_through_an_auto_anchor() -> None:
    # c matches b's height, which itself matched a's height -> resolved in order.
    text = (
        'room a "A" 30x25 root\nroom b "B" 20x? right-of a\nroom c "C" 15x? right-of b'
    )
    assert dims(text, "c") == (15, 25)


@pytest.mark.parametrize(
    "source",
    [
        # '?' width needs an up/down relation; b only has a left/right one.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" ?x10 right-of a',
            id="auto-width-no-updown-relation",
        ),
        # '?' height needs a left/right relation; b only has an up/down one.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x? down-of a',
            id="auto-height-no-leftright-relation",
        ),
        # the root has no anchor to size against.
        pytest.param('room a "A" ?x20 root', id="auto-on-root"),
    ],
)
def test_unresolvable_auto_dim_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


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
